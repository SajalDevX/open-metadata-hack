"""FastAPI application wiring the live incident copilot service.

Endpoints:
  POST /webhooks/incidents      — receive OpenMetadata alert payloads, run pipeline, persist, deliver.
  GET  /incidents               — list recent incidents.
  GET  /incidents/{id}          — fetch one incident's full brief.
  GET  /incidents/{id}/view     — rendered HTML brief.
  GET  /health                  — liveness + connected-integrations snapshot.
  GET  /metrics                 — lightweight counters for ops.
  GET  /admin/retry-queue       — inspect pending Slack retries.
  POST /admin/retry-now         — force an immediate retry sweep.
  POST /slack/actions           — Slack interactivity handler (ack/approve/deny).
  POST /slack/commands          — Slack slash command: /metadata search <query>.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from incident_copilot.background_retry import retry_pending_deliveries
from incident_copilot.brief_renderer import render_brief_html
from incident_copilot.config import AppConfig, load_config
from incident_copilot.dashboard_renderer import render_dashboard_html
from incident_copilot.delivery_queue import DeliveryQueue
from incident_copilot.om_poller import poll_once
from incident_copilot.orchestrator import run_pipeline
from incident_copilot.slack_actions import (
    SlackAuthorizationError,
    SlackActionError,
    apply_action,
    parse_action_payload,
    post_ephemeral_via_bot,
    render_slack_response,
    verify_slack_signature,
)
from incident_copilot.slack_sender import build_slack_sender
from incident_copilot.store import IncidentStore
from incident_copilot.webhook_parser import parse_om_alert_payload


log = logging.getLogger("incident_copilot")
_WEBHOOK_REPLAY_WINDOW_SECONDS = 300


def _is_canonical_envelope(payload: dict) -> bool:
    return isinstance(payload, dict) and all(k in payload for k in ("incident_id", "entity_fqn", "test_case_id"))


def _looks_like_om_alert(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    entity = payload.get("entity")
    if not isinstance(entity, dict):
        return False
    return bool(entity.get("id") or entity.get("fullyQualifiedName") or entity.get("entityLink"))


def _verify_webhook_signature(raw_body: bytes, timestamp: str, signature: str, secret: str) -> bool:
    if not (raw_body is not None and timestamp and signature and secret):
        return False
    try:
        ts_int = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs(time.time() - ts_int) > _WEBHOOK_REPLAY_WINDOW_SECONDS:
        return False
    basestring = f"v1:{timestamp}:".encode() + raw_body
    expected = "v1=" + hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _require_api_key(request: Request, configured_key: str | None, *, required: bool) -> None:
    if not configured_key:
        if required:
            raise HTTPException(status_code=503, detail="COPILOT_API_KEY not configured")
        return
    provided = request.headers.get("x-api-key", "")
    if not provided or not hmac.compare_digest(provided, configured_key):
        raise HTTPException(status_code=401, detail="invalid API key")


def create_app(config: AppConfig | None = None, retry_interval_seconds: float = 30.0) -> FastAPI:
    config_provided = config is not None
    cfg = config if config is not None else load_config()
    store = IncidentStore(cfg.db_path)
    queue = DeliveryQueue(cfg.db_path)

    async def _retry_loop():
        while True:
            try:
                sender = build_slack_sender()
                retry_pending_deliveries(store=store, queue=queue, slack_sender=sender)
            except Exception as exc:  # pragma: no cover — defensive
                log.warning("retry loop error: %s", exc)
            await asyncio.sleep(retry_interval_seconds)

    async def _poll_loop():
        from incident_copilot.openmetadata_client import OpenMetadataClient
        cursor_state = {"cursor": 0}
        while True:
            try:
                om_client = OpenMetadataClient.from_env()

                def _dispatch(payload: dict):
                    envelope = parse_om_alert_payload(payload)
                    existing = store.fetch_by_id(envelope["incident_id"])
                    if existing:
                        return None  # dedup — already seen
                    slack_sender = build_slack_sender() or (lambda _: False)
                    result = run_pipeline(envelope, None, slack_sender=slack_sender)
                    delivery = result["delivery"]["delivery"]
                    store.save_brief(
                        brief=result["brief"],
                        delivery_status=delivery.slack_status if delivery.primary_output == "slack" else delivery.local_status,
                        primary_output=delivery.primary_output,
                    )
                    if cfg.has_slack and delivery.primary_output == "local_mirror":
                        queue.enqueue(result["brief"]["incident_id"], reason="SLACK_SEND_FAILED")
                    return result

                summary = poll_once(om_client=om_client, dispatch_fn=_dispatch, cursor=cursor_state["cursor"])
                cursor_state["cursor"] = summary.get("new_cursor", cursor_state["cursor"])
            except Exception as exc:  # pragma: no cover — defensive
                log.warning("poll loop error: %s", exc)
            await asyncio.sleep(cfg.poller_interval_seconds)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        tasks = []
        if cfg.has_slack and retry_interval_seconds > 0:
            tasks.append(asyncio.create_task(_retry_loop()))
        if cfg.enable_poller and cfg.has_openmetadata:
            tasks.append(asyncio.create_task(_poll_loop()))
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()

    app = FastAPI(title="OpenMetadata Incident Copilot", version="0.4.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.store = store
    app.state.queue = queue
    app.state.retry_interval = retry_interval_seconds

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "has_openmetadata": cfg.has_openmetadata,
            "has_slack": cfg.has_slack,
            "has_ai": cfg.has_ai,
            "db_path": cfg.db_path,
            "retry_interval_seconds": retry_interval_seconds,
        }

    @app.get("/metrics")
    def metrics(request: Request):
        _require_api_key(request, cfg.api_key, required=False)
        return {
            "incident_count": store.count(),
            "pending_retries": len(queue.pending(limit=1000)),
        }

    @app.post("/webhooks/incidents")
    async def ingest_incident(request: Request):
        raw = await request.body()
        secret = cfg.webhook_signing_secret
        if secret:
            ts = request.headers.get("x-webhook-timestamp", "")
            sig = request.headers.get("x-webhook-signature", "")
            if not _verify_webhook_signature(raw, ts, sig, secret):
                raise HTTPException(status_code=401, detail="invalid webhook signature")
        else:
            webhook_secret = os.environ.get("WEBHOOK_SECRET")
            if webhook_secret:
                auth = request.headers.get("Authorization", "")
                token = auth.removeprefix("Bearer ").strip()
                if token != webhook_secret:
                    raise HTTPException(status_code=401, detail="invalid webhook secret")
            elif not config_provided:
                raise HTTPException(status_code=503, detail="COPILOT_WEBHOOK_SECRET not configured")

        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:  # pragma: no cover - shared parse guard
            raise HTTPException(status_code=400, detail="body must be JSON")
        if _is_canonical_envelope(payload):
            raise HTTPException(status_code=400, detail="canonical incident envelopes are not accepted on webhook endpoint")
        if not _looks_like_om_alert(payload):
            raise HTTPException(status_code=400, detail="unsupported webhook payload shape")

        envelope = parse_om_alert_payload(payload)
        slack_sender = build_slack_sender() or (lambda _: False)

        try:
            result = run_pipeline(envelope, None, slack_sender=slack_sender)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"pipeline failure: {exc}") from exc

        delivery = result["delivery"]["delivery"]
        incident_id = result["brief"]["incident_id"]

        store.save_brief(
            brief=result["brief"],
            delivery_status=delivery.slack_status if delivery.primary_output == "slack" else delivery.local_status,
            primary_output=delivery.primary_output,
        )

        # Enqueue retry when Slack was configured and failed
        if cfg.has_slack and delivery.primary_output == "local_mirror":
            queue.enqueue(incident_id, reason="SLACK_SEND_FAILED")

        return {
            "incident_id": incident_id,
            "brief": result["brief"],
            "delivery": {
                "primary_output": delivery.primary_output,
                "slack_status": delivery.slack_status,
                "local_status": delivery.local_status,
                "degraded_reason_codes": delivery.degraded_reason_codes or [],
            },
            "fallback_reason_codes": result["fallback_reason_codes"],
        }

    @app.get("/incidents")
    def list_incidents(request: Request, limit: int = 50):
        _require_api_key(request, cfg.api_key, required=False)
        rows = store.list_recent(limit=limit)
        return {"count": len(rows), "items": rows}

    @app.get("/incidents/{incident_id}")
    def fetch_incident(incident_id: str, request: Request):
        _require_api_key(request, cfg.api_key, required=False)
        row = store.fetch_by_id(incident_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"incident {incident_id} not found")
        return row

    @app.get("/incidents/{incident_id}/view", response_class=HTMLResponse)
    def view_incident(incident_id: str, request: Request):
        _require_api_key(request, cfg.api_key, required=False)
        row = store.fetch_by_id(incident_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"incident {incident_id} not found")
        return HTMLResponse(render_brief_html(row["brief"]))

    @app.post("/slack/actions")
    async def slack_actions(request: Request):
        secret = os.environ.get("SLACK_SIGNING_SECRET")
        if not secret:
            raise HTTPException(status_code=503, detail="SLACK_SIGNING_SECRET not configured")

        raw = await request.body()
        ts = request.headers.get("x-slack-request-timestamp", "")
        sig = request.headers.get("x-slack-signature", "")
        if not verify_slack_signature(raw, ts, sig, secret):
            raise HTTPException(status_code=401, detail="invalid Slack signature")

        try:
            parsed = parse_action_payload(raw)
        except SlackActionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        try:
            apply_action(store, parsed["incident_id"], parsed["action"], parsed["user_name"], parsed.get("user_id", ""))
        except SlackAuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except SlackActionError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        action_label = {"ack": "Acknowledged", "approve": "Approved", "deny": "Denied"}.get(
            parsed["action"], parsed["action"].title()
        )
        post_ephemeral_via_bot(
            channel_id=parsed.get("channel_id", ""),
            user_id=parsed.get("user_id", ""),
            text=f":white_check_mark: {action_label} incident `{parsed['incident_id']}` — recorded by copilot.",
        )

        return render_slack_response(parsed["action"], parsed["user_name"], parsed["incident_id"])

    @app.get("/rca-summary")
    def rca_summary():
        return store.rca_summary()

    @app.post("/slack/commands")
    async def slack_commands(request: Request):
        raw = await request.body()
        secret = os.environ.get("SLACK_SIGNING_SECRET")
        if secret:
            ts = request.headers.get("x-slack-request-timestamp", "")
            sig = request.headers.get("x-slack-signature", "")
            if not verify_slack_signature(raw, ts, sig, secret):
                raise HTTPException(status_code=401, detail="invalid Slack signature")

        params = parse_qs(raw.decode("utf-8", errors="replace"))
        text = (params.get("text") or [""])[0].strip()
        if text.lower().startswith("search "):
            text = text[7:].strip()

        if not text:
            return JSONResponse({
                "response_type": "ephemeral",
                "text": "Usage: `/metadata search <query>` — search OpenMetadata tables and assets.",
            })

        if not cfg.has_openmetadata:
            return JSONResponse({
                "response_type": "ephemeral",
                "text": (
                    ":warning: OpenMetadata is not configured. "
                    "Set `OPENMETADATA_BASE_URL` and `OPENMETADATA_JWT_TOKEN` to enable search."
                ),
            })

        try:
            from incident_copilot.openmetadata_client import OpenMetadataClient
            om = OpenMetadataClient.from_env()
            results = om.search_entities(text, limit=5)
        except Exception as exc:
            log.warning("slack command search error: %s", exc)
            results = []

        if not results:
            return JSONResponse({
                "response_type": "ephemeral",
                "text": f":mag: No results found for *{text}* in OpenMetadata.",
            })

        blocks: list[dict] = [
            {"type": "section", "text": {"type": "mrkdwn", "text": f":mag: *Search results for '{text}'*"}},
            {"type": "divider"},
        ]
        for hit in results:
            fqn = hit.get("fullyQualifiedName") or hit.get("name") or "unknown"
            desc = (hit.get("description") or "").strip()
            owners = ", ".join(
                o.get("name") or o.get("displayName") or ""
                for o in (hit.get("owners") or [])
                if o.get("name") or o.get("displayName")
            ) or "unowned"
            label = f"*{fqn}*"
            if desc:
                label += f"\n{desc[:120]}"
            label += f"\n:bust_in_silhouette: Owner: {owners}"
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": label}})

        return JSONResponse({"response_type": "ephemeral", "blocks": blocks})

    @app.get("/admin/retry-queue")
    def retry_queue_snapshot(request: Request):
        _require_api_key(request, cfg.api_key, required=True)
        return {"pending": queue.pending(limit=1000)}

    @app.post("/admin/retry-now")
    def retry_now(request: Request):
        _require_api_key(request, cfg.api_key, required=True)
        sender = build_slack_sender()
        if sender is None:
            return JSONResponse({"retried": 0, "error": "SLACK_WEBHOOK_URL not configured"}, status_code=400)
        return retry_pending_deliveries(store=store, queue=queue, slack_sender=sender)

    @app.post("/slack/digest")
    async def slack_digest():
        """Post a daily summary of recent incidents to Slack."""
        if not cfg.has_slack:
            return JSONResponse({"status": "not_configured", "reason": "SLACK_WEBHOOK_URL not set"}, status_code=400)

        summary = store.rca_summary(limit=200)
        rows = store.list_recent(limit=10)
        total = summary["total_incidents"]

        lines = [f":bar_chart: *OpenMetadata Incident Copilot — Daily Digest*\n*{total} incidents* in the last batch\n"]
        for bucket in summary["signal_types"][:5]:
            sig = bucket["signal_type"].replace("_", " ").title()
            lines.append(f"• {sig}: {bucket['count']} incidents ({bucket['approval_required']} requiring approval)")

        if rows:
            lines.append("\n*Most recent:*")
            for row in rows[:5]:
                iid = row["incident_id"]
                pol = ":rotating_light:" if row["policy_state"] == "approval_required" else ":white_check_mark:"
                lines.append(f"  {pol} `{iid}`")

        text = "\n".join(lines)
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]

        sender = build_slack_sender()
        sent = False
        if sender:
            try:
                sent = bool(sender({"text": text, "blocks": blocks}))
            except Exception as exc:
                log.warning("digest send error: %s", exc)

        return {"status": "sent" if sent else "fallback", "total_incidents": total, "signal_types": len(summary["signal_types"]), "text": text}

    @app.get("/admin/dead-letter")
    def dead_letter_queue():
        return {"dead_letters": queue.dead_letters(limit=100)}

    @app.delete("/admin/dead-letter/{incident_id}")
    def discard_dead_letter(incident_id: str):
        removed = queue.discard_dead_letter(incident_id)
        if not removed:
            raise HTTPException(status_code=404, detail=f"{incident_id} not found in dead-letter queue")
        return {"discarded": incident_id}

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        _require_api_key(request, cfg.api_key, required=False)
        rows = store.list_recent(limit=50)
        return HTMLResponse(render_dashboard_html(
            rows=rows,
            total=store.count(),
            has_openmetadata=cfg.has_openmetadata,
            has_slack=cfg.has_slack,
            has_ai=cfg.has_ai,
        ))

    @app.get("/api")
    def api_root(request: Request):
        _require_api_key(request, cfg.api_key, required=False)
        return JSONResponse({
            "service": "openmetadata-incident-copilot",
            "endpoints": [
                "POST /webhooks/incidents",
                "GET  /incidents",
                "GET  /incidents/{id}",
                "GET  /incidents/{id}/view",
                "GET  /health",
                "GET  /metrics",
                "GET  /admin/retry-queue",
                "POST /admin/retry-now",
                "POST /slack/actions         — Slack interactivity (ack/approve/deny)",
                "POST /slack/commands        — Slack slash command (/metadata search <query>)",
                "GET  /                      — HTML dashboard",
            ],
        })

    return app
