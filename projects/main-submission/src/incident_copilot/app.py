"""FastAPI application wiring the live incident copilot service.

Endpoints:
  POST /webhooks/incidents   — receive OpenMetadata alert payloads, run pipeline, persist, deliver.
  GET  /incidents            — list recent incidents.
  GET  /incidents/{id}       — fetch one incident's full brief.
  GET  /incidents/{id}/view  — rendered HTML brief.
  GET  /health               — liveness + connected-integrations snapshot.
  GET  /metrics              — lightweight counters for ops.
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from incident_copilot.brief_renderer import render_brief_html
from incident_copilot.config import AppConfig, load_config
from incident_copilot.orchestrator import run_pipeline
from incident_copilot.slack_sender import build_slack_sender
from incident_copilot.store import IncidentStore
from incident_copilot.webhook_parser import parse_om_alert_payload


def create_app(config: AppConfig | None = None) -> FastAPI:
    cfg = config or load_config()
    store = IncidentStore(cfg.db_path)

    app = FastAPI(title="OpenMetadata Incident Copilot", version="0.3.0")
    app.state.config = cfg
    app.state.store = store

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "has_openmetadata": cfg.has_openmetadata,
            "has_slack": cfg.has_slack,
            "has_ai": cfg.has_ai,
            "db_path": cfg.db_path,
        }

    @app.get("/metrics")
    def metrics():
        return {"incident_count": store.count()}

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
        store.save_brief(
            brief=result["brief"],
            delivery_status=delivery.slack_status if delivery.primary_output == "slack" else delivery.local_status,
            primary_output=delivery.primary_output,
        )

        return {
            "incident_id": result["brief"]["incident_id"],
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

    @app.get("/")
    def root():
        return JSONResponse({
            "service": "openmetadata-incident-copilot",
            "endpoints": [
                "POST /webhooks/incidents",
                "GET  /incidents",
                "GET  /incidents/{id}",
                "GET  /incidents/{id}/view",
                "GET  /health",
                "GET  /metrics",
            ],
        })

    return app
