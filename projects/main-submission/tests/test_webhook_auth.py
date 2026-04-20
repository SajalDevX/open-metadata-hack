"""Tests for optional bearer-token auth on POST /webhooks/incidents."""
import pytest
from fastapi.testclient import TestClient

from incident_copilot.app import create_app
from incident_copilot.config import AppConfig

_PAYLOAD = {
    "entity": {
        "id": "test-tc-auth",
        "fullyQualifiedName": "svc.db.table",
        "testCaseResult": {"testCaseStatus": "Failed", "result": "null ratio exceeded"},
    }
}


def _make_config(**overrides) -> AppConfig:
    defaults = dict(
        host="127.0.0.1", port=8080, db_path=":memory:", default_channel="#test",
        openmetadata_base_url=None, openmetadata_jwt_token=None, openmetadata_mcp_url=None,
        slack_webhook_url=None, openrouter_api_key=None, use_om_mcp=False,
        enable_poller=False, poller_interval_seconds=60.0,
    )
    defaults.update(overrides)
    return AppConfig(**defaults)


def test_webhook_no_secret_allows_unauthenticated(monkeypatch, tmp_path):
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    app = create_app(_make_config(db_path=str(tmp_path / "test.db")), retry_interval_seconds=0)
    client = TestClient(app)
    resp = client.post("/webhooks/incidents", json=_PAYLOAD)
    assert resp.status_code == 200


def test_webhook_with_secret_rejects_missing_auth(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", "supersecret")
    app = create_app(_make_config(), retry_interval_seconds=0)
    client = TestClient(app)
    resp = client.post("/webhooks/incidents", json=_PAYLOAD)
    assert resp.status_code == 401


def test_webhook_with_secret_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", "supersecret")
    app = create_app(_make_config(), retry_interval_seconds=0)
    client = TestClient(app)
    resp = client.post("/webhooks/incidents", json=_PAYLOAD, headers={"Authorization": "Bearer wrongtoken"})
    assert resp.status_code == 401


def test_webhook_with_secret_accepts_correct_token(monkeypatch, tmp_path):
    monkeypatch.setenv("WEBHOOK_SECRET", "supersecret")
    app = create_app(_make_config(db_path=str(tmp_path / "test.db")), retry_interval_seconds=0)
    client = TestClient(app)
    resp = client.post("/webhooks/incidents", json=_PAYLOAD, headers={"Authorization": "Bearer supersecret"})
    assert resp.status_code == 200
    assert "incident_id" in resp.json()
