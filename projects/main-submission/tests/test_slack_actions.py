import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from incident_copilot.app import create_app


def _sign(body: str, secret: str, ts: str) -> str:
    basestring = f"v0:{ts}:{body}".encode()
    mac = hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    return f"v0={mac}"


def _action_body(incident_id: str, action: str = "ack") -> str:
    payload = {
        "type": "block_actions",
        "user": {"id": "U123", "name": "steward"},
        "actions": [{"action_id": action, "value": incident_id}],
    }
    return urlencode({"payload": json.dumps(payload)})


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "test-secret")
    monkeypatch.setattr(
        "incident_copilot.app.run_pipeline",
        lambda e, o, slack_sender, mirror_writer=None: {
            "brief": {
                "incident_id": e["incident_id"],
                "policy_state": "approval_required",
                "what_failed": {"text": "x", "evidence_refs": []},
                "what_is_impacted": {"text": "x", "evidence_refs": []},
                "who_acts_first": {"text": "x", "evidence_refs": []},
                "what_to_do_next": {"text": "x", "evidence_refs": []},
            },
            "delivery": {
                "delivery": type("D", (), {"slack_status": "sent", "local_status": "rendered", "primary_output": "slack", "degraded_reason_codes": []})(),
                "slack_payload": {}, "local_mirror_payload": {},
            },
            "rca": None, "scored_assets": [], "recommendation": None,
            "fallback_reason_codes": [],
        },
    )
    return TestClient(create_app(retry_interval_seconds=0))


def _seed(client, incident_id: str):
    return client.post("/webhooks/incidents", json={
        "incident_id": incident_id, "entity_fqn": "svc.db.x",
        "test_case_id": "tc", "severity": "high",
        "occurred_at": "2026-04-18T00:00:00Z", "raw_ref": "x",
    })


def test_valid_signature_accepts_ack(client):
    _seed(client, "inc-ack-1")
    body = _action_body("inc-ack-1", "ack")
    ts = str(int(time.time()))
    sig = _sign(body, "test-secret", ts)
    r = client.post(
        "/slack/actions",
        content=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": sig,
        },
    )
    assert r.status_code == 200
    body_json = r.json()
    # Response is now a Slack-renderable ephemeral message
    assert body_json["response_type"] == "ephemeral"
    assert body_json["replace_original"] is False
    assert "inc-ack-1" in body_json["text"]
    assert "Acknowledged" in body_json["text"]


def test_invalid_signature_rejected(client):
    _seed(client, "inc-ack-2")
    body = _action_body("inc-ack-2", "ack")
    ts = str(int(time.time()))
    r = client.post(
        "/slack/actions",
        content=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": "v0=deadbeef",
        },
    )
    assert r.status_code == 401


def test_stale_timestamp_rejected(client):
    _seed(client, "inc-ack-3")
    body = _action_body("inc-ack-3", "ack")
    old_ts = str(int(time.time()) - 3600)  # 1 hour old
    sig = _sign(body, "test-secret", old_ts)
    r = client.post(
        "/slack/actions",
        content=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Slack-Request-Timestamp": old_ts,
            "X-Slack-Signature": sig,
        },
    )
    assert r.status_code == 401


def test_approve_updates_delivery_status(client):
    _seed(client, "inc-approve-1")
    body = _action_body("inc-approve-1", "approve")
    ts = str(int(time.time()))
    sig = _sign(body, "test-secret", ts)
    r = client.post(
        "/slack/actions", content=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": sig,
        },
    )
    assert r.status_code == 200
    incident = client.get("/incidents/inc-approve-1").json()
    assert incident["delivery_status"].startswith("acked") or "approved" in incident["delivery_status"]


def test_deny_is_recorded(client):
    _seed(client, "inc-deny-1")
    body = _action_body("inc-deny-1", "deny")
    ts = str(int(time.time()))
    sig = _sign(body, "test-secret", ts)
    r = client.post(
        "/slack/actions", content=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": sig,
        },
    )
    assert r.status_code == 200
    assert "Denied" in r.json()["text"]
    assert "inc-deny-1" in r.json()["text"]


def test_missing_secret_returns_503(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.delenv("SLACK_SIGNING_SECRET", raising=False)
    client = TestClient(create_app(retry_interval_seconds=0))
    r = client.post("/slack/actions", content="", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 503


def test_unknown_incident_returns_404(client):
    body = _action_body("does-not-exist", "ack")
    ts = str(int(time.time()))
    sig = _sign(body, "test-secret", ts)
    r = client.post(
        "/slack/actions", content=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": sig,
        },
    )
    assert r.status_code == 404
