"""Black-box service e2e test: signed webhook -> persisted brief -> protected reads."""
import hashlib
import hmac
import json
import time

from fastapi.testclient import TestClient

from incident_copilot.app import create_app


def _sign_webhook(body: bytes, secret: str, ts: str) -> str:
    basestring = f"v1:{ts}:".encode() + body
    mac = hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    return f"v1={mac}"


def _post_signed_webhook(client: TestClient, payload: dict, secret: str):
    body = json.dumps(payload).encode("utf-8")
    ts = str(int(time.time()))
    return client.post(
        "/webhooks/incidents",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Timestamp": ts,
            "X-Webhook-Signature": _sign_webhook(body, secret, ts),
        },
    )


def test_live_app_webhook_to_read_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_DB_PATH", str(tmp_path / "incidents.db"))
    monkeypatch.setenv("COPILOT_WEBHOOK_SECRET", "om-e2e-secret")
    monkeypatch.setenv("COPILOT_API_KEY", "api-e2e-key")
    monkeypatch.delenv("OPENMETADATA_BASE_URL", raising=False)
    monkeypatch.delenv("OPENMETADATA_JWT_TOKEN", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK", raising=False)

    client = TestClient(create_app(retry_interval_seconds=0))
    webhook = {
        "entity": {
            "id": "tc-e2e-1",
            "fullyQualifiedName": "demo_mysql.customer_analytics.raw.customer_profiles",
            "testDefinition": {"name": "columnValueNullRatioExceeded"},
            "testCaseResult": {
                "testCaseStatus": "Failed",
                "result": "null ratio on customer_id exceeded 15%",
            },
        },
        "timestamp": 1713436800000,
    }

    ingest = _post_signed_webhook(client, webhook, secret="om-e2e-secret")
    assert ingest.status_code == 200
    incident_id = ingest.json()["incident_id"]
    assert incident_id.startswith("om-")

    unauthorized = client.get("/incidents")
    assert unauthorized.status_code == 401
    assert client.get("/").status_code == 401
    assert client.get("/api").status_code == 401

    auth_headers = {"X-API-Key": "api-e2e-key"}
    assert client.get("/", headers=auth_headers).status_code == 200
    assert client.get("/api", headers=auth_headers).status_code == 200
    listed = client.get("/incidents", headers=auth_headers)
    assert listed.status_code == 200
    assert any(item["incident_id"] == incident_id for item in listed.json()["items"])

    fetched = client.get(f"/incidents/{incident_id}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["brief"]["incident_id"] == incident_id

    rendered = client.get(f"/incidents/{incident_id}/view", headers=auth_headers)
    assert rendered.status_code == 200
    assert "text/html" in rendered.headers["content-type"]
    assert incident_id in rendered.text
