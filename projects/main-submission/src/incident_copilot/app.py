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
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

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
    SlackActionError,
    apply_action,
    parse_action_payload,
    render_slack_response,
    verify_slack_signature,
)
from incident_copilot.slack_sender import build_slack_sender
from incident_copilot.store import IncidentStore
from incident_copilot.webhook_parser import parse_om_alert_payload


log = logging.getLogger("incident_copilot")


def create_app(config: AppConfig | None = None, retry_interval_seconds: float = 30.0) -> FastAPI:
    cfg = config or load_config()
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
    def metrics():
        return {
            "incident_count": store.count(),
            "pending_retries": len(queue.pending(limit=1000)),
        }

    @app.post("/webhooks/incidents")
    async def ingest_incident(request: Request):
        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="body must be JSON")

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
    def list_incidents(limit: int = 50):
        rows = store.list_recent(limit=limit)
        return {"count": len(rows), "items": rows}

    @app.get("/incidents/{incident_id}")
    def fetch_incident(incident_id: str):
        row = store.fetch_by_id(incident_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"incident {incident_id} not found")
        return row

    @app.get("/incidents/{incident_id}/view", response_class=HTMLResponse)
    def view_incident(incident_id: str):
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
            apply_action(store, parsed["incident_id"], parsed["action"], parsed["user_name"])
        except SlackActionError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        return render_slack_response(parsed["action"], parsed["user_name"], parsed["incident_id"])

    @app.get("/admin/retry-queue")
    def retry_queue_snapshot():
        return {"pending": queue.pending(limit=1000)}

    @app.post("/admin/retry-now")
    def retry_now():
        sender = build_slack_sender()
        if sender is None:
            return JSONResponse({"retried": 0, "error": "SLACK_WEBHOOK_URL not configured"}, status_code=400)
        return retry_pending_deliveries(store=store, queue=queue, slack_sender=sender)

    @app.get("/", response_class=HTMLResponse)
    def dashboard():
        rows = store.list_recent(limit=50)
        return HTMLResponse(render_dashboard_html(
            rows=rows,
            total=store.count(),
            has_openmetadata=cfg.has_openmetadata,
            has_slack=cfg.has_slack,
            has_ai=cfg.has_ai,
        ))

    @app.get("/api")
    def api_root():
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
                "GET  /                    — HTML dashboard",
            ],
        })

    return app
