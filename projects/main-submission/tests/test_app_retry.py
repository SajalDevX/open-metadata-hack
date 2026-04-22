"""Integration tests for the webhook → delivery-queue → retry-endpoint wiring."""
import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from incident_copilot.app import create_app


SAMPLE_OM_PAYLOAD = {
    "entity": {
        "id": "tc-retry-1",
        "fullyQualifiedName": "svc.db.orders",
        "testCaseResult": {"testCaseStatus": "Failed", "result": "null ratio exceeded"},
    }
}


def _sign_webhook(body: bytes, secret: str, ts: str) -> str:
    basestring = f"v1:{ts}:".encode() + body
    mac = hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    return f"v1={mac}"


def _post_webhook(client, payload: dict, secret: str = "om-test-secret"):
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


def _fake_run_pipeline(raw_event, om_data, slack_sender, mirror_writer=None):
    slack_ok = bool(slack_sender({"test": True}))
    delivery = type(
        "D", (),
        {
            "slack_status": "sent" if slack_ok else "failed",
            "local_status": "rendered",
            "primary_output": "slack" if slack_ok else "local_mirror",
            "degraded_reason_codes": [] if slack_ok else ["SLACK_SEND_FAILED"],
        },
    )()
    return {
        "brief": {
            "incident_id": raw_event["incident_id"],
            "policy_state": "allowed",
            "what_failed": {"text": "x", "evidence_refs": []},
            "what_is_impacted": {"text": "x", "evidence_refs": []},
            "who_acts_first": {"text": "x", "evidence_refs": []},
            "what_to_do_next": {"text": "x", "evidence_refs": []},
        },
        "delivery": {"delivery": delivery, "slack_payload": {}, "local_mirror_payload": {}},
        "rca": None, "scored_assets": [], "recommendation": None,
        "fallback_reason_codes": [],
    }


@pytest.fixture
def client_with_slack(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("COPILOT_WEBHOOK_SECRET", "om-test-secret")
    monkeypatch.setenv("COPILOT_API_KEY", "admin-key")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/x")
    monkeypatch.setattr("incident_copilot.app.run_pipeline", _fake_run_pipeline)
    # Force Slack sender to fail initially
    failing = lambda _p: False
    monkeypatch.setattr("incident_copilot.app.build_slack_sender", lambda: failing)
    app = create_app(retry_interval_seconds=0)  # disable background loop during tests
    return TestClient(app)


def test_failed_slack_enqueues_retry(client_with_slack):
    r = _post_webhook(client_with_slack, SAMPLE_OM_PAYLOAD)
    assert r.status_code == 200
    assert r.json()["delivery"]["primary_output"] == "local_mirror"

    snap = client_with_slack.get("/admin/retry-queue", headers={"X-API-Key": "admin-key"}).json()
    assert len(snap["pending"]) == 1
    assert snap["pending"][0]["incident_id"] == r.json()["incident_id"]


def test_metrics_reports_pending(client_with_slack):
    _post_webhook(client_with_slack, SAMPLE_OM_PAYLOAD)
    m = client_with_slack.get("/metrics", headers={"X-API-Key": "admin-key"}).json()
    assert m["incident_count"] == 1
    assert m["pending_retries"] == 1


def test_retry_now_with_succeeding_sender(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("COPILOT_WEBHOOK_SECRET", "om-test-secret")
    monkeypatch.setenv("COPILOT_API_KEY", "admin-key")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/x")
    monkeypatch.setattr("incident_copilot.app.run_pipeline", _fake_run_pipeline)

    call_count = {"n": 0}

    def sender(_payload):
        call_count["n"] += 1
        return call_count["n"] > 1  # first call fails, retry succeeds

    monkeypatch.setattr("incident_copilot.app.build_slack_sender", lambda: sender)
    app = create_app(retry_interval_seconds=0)
    client = TestClient(app)

    post = _post_webhook(client, SAMPLE_OM_PAYLOAD)
    assert post.json()["delivery"]["primary_output"] == "local_mirror"
    assert client.get("/metrics", headers={"X-API-Key": "admin-key"}).json()["pending_retries"] == 1

    retry = client.post("/admin/retry-now", headers={"X-API-Key": "admin-key"}).json()
    assert retry["retried"] == 1
    assert retry["succeeded"] == 1
    assert client.get("/metrics", headers={"X-API-Key": "admin-key"}).json()["pending_retries"] == 0


def test_retry_now_without_webhook_returns_400(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("COPILOT_API_KEY", "admin-key")
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK", raising=False)
    monkeypatch.setattr("incident_copilot.app.run_pipeline", _fake_run_pipeline)
    monkeypatch.setattr("incident_copilot.app.build_slack_sender", lambda: None)
    app = create_app(retry_interval_seconds=0)
    client = TestClient(app)
    r = client.post("/admin/retry-now", headers={"X-API-Key": "admin-key"})
    assert r.status_code == 400


def test_admin_retry_queue_requires_api_key(client_with_slack):
    r = client_with_slack.get("/admin/retry-queue")
    assert r.status_code == 401


def test_admin_retry_now_rejects_invalid_api_key(client_with_slack):
    r = client_with_slack.post("/admin/retry-now", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401
