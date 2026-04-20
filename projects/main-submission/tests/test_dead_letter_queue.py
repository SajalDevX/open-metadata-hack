"""Tests for dead-letter queue — DeliveryQueue.dead_letters() and /admin/dead-letter endpoints."""
import pytest
from fastapi.testclient import TestClient

from incident_copilot.app import create_app
from incident_copilot.config import AppConfig
from incident_copilot.delivery_queue import DeliveryQueue


def _make_config(**overrides) -> AppConfig:
    defaults = dict(
        host="127.0.0.1", port=8080, db_path=":memory:", default_channel="#test",
        openmetadata_base_url=None, openmetadata_jwt_token=None, openmetadata_mcp_url=None,
        slack_webhook_url=None, openrouter_api_key=None, use_om_mcp=False,
        enable_poller=False, poller_interval_seconds=60.0,
    )
    defaults.update(overrides)
    return AppConfig(**defaults)


def test_dead_letters_empty_by_default(tmp_path):
    q = DeliveryQueue(str(tmp_path / "test.db"))
    assert q.dead_letters() == []


def test_dead_letters_returns_exhausted_entries(tmp_path):
    q = DeliveryQueue(str(tmp_path / "test.db"))
    q.enqueue("inc-1", "SLACK_SEND_FAILED")
    for _ in range(5):
        q.mark_failed("inc-1", "connection refused")
    result = q.dead_letters(max_attempts=5)
    assert len(result) == 1
    assert result[0]["incident_id"] == "inc-1"
    assert result[0]["attempts"] == 5
    assert result[0]["last_error"] == "connection refused"


def test_dead_letters_excludes_pending_entries(tmp_path):
    q = DeliveryQueue(str(tmp_path / "test.db"))
    q.enqueue("inc-active", "SLACK_SEND_FAILED")
    q.enqueue("inc-dead", "SLACK_SEND_FAILED")
    for _ in range(5):
        q.mark_failed("inc-dead", "timeout")
    dead = q.dead_letters(max_attempts=5)
    ids = [d["incident_id"] for d in dead]
    assert "inc-dead" in ids
    assert "inc-active" not in ids


def test_discard_dead_letter_removes_entry(tmp_path):
    q = DeliveryQueue(str(tmp_path / "test.db"))
    q.enqueue("inc-1", "SLACK_SEND_FAILED")
    for _ in range(5):
        q.mark_failed("inc-1", "err")
    assert len(q.dead_letters()) == 1
    removed = q.discard_dead_letter("inc-1")
    assert removed is True
    assert q.dead_letters() == []


def test_discard_dead_letter_returns_false_for_missing(tmp_path):
    q = DeliveryQueue(str(tmp_path / "test.db"))
    assert q.discard_dead_letter("nonexistent") is False


def test_api_dead_letter_endpoint_empty(tmp_path):
    db = str(tmp_path / "test.db")
    app = create_app(_make_config(db_path=db), retry_interval_seconds=0)
    client = TestClient(app)
    resp = client.get("/admin/dead-letter")
    assert resp.status_code == 200
    assert resp.json() == {"dead_letters": []}


def test_api_dead_letter_endpoint_shows_exhausted(tmp_path):
    db = str(tmp_path / "test.db")
    app = create_app(_make_config(db_path=db), retry_interval_seconds=0)
    client = TestClient(app)

    q = DeliveryQueue(db)
    q.enqueue("inc-dead-1", "SLACK_SEND_FAILED")
    for _ in range(5):
        q.mark_failed("inc-dead-1", "503 error")

    resp = client.get("/admin/dead-letter")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["dead_letters"]) == 1
    assert body["dead_letters"][0]["incident_id"] == "inc-dead-1"


def test_api_discard_dead_letter(tmp_path):
    db = str(tmp_path / "test.db")
    app = create_app(_make_config(db_path=db), retry_interval_seconds=0)
    client = TestClient(app)

    q = DeliveryQueue(db)
    q.enqueue("inc-dead-1", "SLACK_SEND_FAILED")
    for _ in range(5):
        q.mark_failed("inc-dead-1", "err")

    resp = client.delete("/admin/dead-letter/inc-dead-1")
    assert resp.status_code == 200
    assert resp.json()["discarded"] == "inc-dead-1"

    resp2 = client.get("/admin/dead-letter")
    assert resp2.json()["dead_letters"] == []


def test_api_discard_dead_letter_404_for_missing(tmp_path):
    db = str(tmp_path / "test.db")
    app = create_app(_make_config(db_path=db), retry_interval_seconds=0)
    client = TestClient(app)
    resp = client.delete("/admin/dead-letter/nonexistent")
    assert resp.status_code == 404
