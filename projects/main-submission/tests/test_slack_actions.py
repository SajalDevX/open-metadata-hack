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


def _sign_webhook(body: bytes, secret: str, ts: str) -> str:
    basestring = f"v1:{ts}:".encode() + body
    mac = hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    return f"v1={mac}"


def _post_signed_webhook(client, payload: dict, secret: str = "om-test-secret"):
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
    monkeypatch.setenv("COPILOT_WEBHOOK_SECRET", "om-test-secret")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "test-secret")
    monkeypatch.setenv("COPILOT_APPROVER_USERS", "U123")
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
    response = _post_signed_webhook(client, {
        "entity": {
            "id": f"tc-{incident_id}",
            "fullyQualifiedName": "svc.db.schema.orders",
            "testCaseResult": {"testCaseStatus": "Failed", "result": "null ratio"},
        }
    })
    assert response.status_code == 200
    return response.json()["incident_id"]


def test_valid_signature_accepts_ack(client):
    incident_id = _seed(client, "inc-ack-1")
    body = _action_body(incident_id, "ack")
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
    # Response replaces the original message so the brief visibly transforms
    assert body_json["replace_original"] is True
    assert incident_id in body_json["text"]
    assert "Acknowledged" in body_json["text"]
    assert "blocks" in body_json


def test_invalid_signature_rejected(client):
    incident_id = _seed(client, "inc-ack-2")
    body = _action_body(incident_id, "ack")
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
    incident_id = _seed(client, "inc-ack-3")
    body = _action_body(incident_id, "ack")
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
    incident_id = _seed(client, "inc-approve-1")
    body = _action_body(incident_id, "approve")
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
    incident = client.get(f"/incidents/{incident_id}").json()
    assert incident["delivery_status"].startswith("acked") or "approved" in incident["delivery_status"]


def test_deny_is_recorded(client):
    incident_id = _seed(client, "inc-deny-1")
    body = _action_body(incident_id, "deny")
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
    assert incident_id in r.json()["text"]


def test_missing_secret_returns_503(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.delenv("SLACK_SIGNING_SECRET", raising=False)
    client = TestClient(create_app(retry_interval_seconds=0))
    r = client.post("/slack/actions", content="", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 503


def test_post_ephemeral_via_bot_returns_false_without_token(monkeypatch):
    from incident_copilot.slack_actions import post_ephemeral_via_bot
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    assert post_ephemeral_via_bot("C123", "U123", "hi") is False


def test_post_ephemeral_via_bot_returns_false_without_channel(monkeypatch):
    from incident_copilot.slack_actions import post_ephemeral_via_bot
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    assert post_ephemeral_via_bot("", "U123", "hi") is False


def test_post_ephemeral_via_bot_posts_when_configured(monkeypatch):
    from incident_copilot.slack_actions import post_ephemeral_via_bot

    captured = {}

    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"ok": true}'

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in req.header_items()}
        captured["body"] = req.data.decode("utf-8")
        return FakeResp()

    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-real")
    ok = post_ephemeral_via_bot("C123", "U456", "hi there", opener=fake_urlopen)
    assert ok is True
    assert captured["url"] == "https://slack.com/api/chat.postEphemeral"
    assert captured["headers"]["authorization"] == "Bearer xoxb-real"
    import json as _json
    body = _json.loads(captured["body"])
    assert body["channel"] == "C123"
    assert body["user"] == "U456"
    assert body["text"] == "hi there"


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


def test_approve_rejected_for_unauthorized_user(client):
    incident_id = _seed(client, "inc-approve-2")
    payload = {
        "type": "block_actions",
        "user": {"id": "U999", "name": "intruder"},
        "actions": [{"action_id": "approve", "value": incident_id}],
    }
    body = urlencode({"payload": json.dumps(payload)})
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
    assert r.status_code == 403
