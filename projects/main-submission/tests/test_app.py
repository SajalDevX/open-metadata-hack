import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from incident_copilot.app import create_app


SAMPLE_PIPELINE_RESULT = {
    "brief": {
        "incident_id": "om-tc-1-123",
        "policy_state": "approval_required",
        "what_failed": {"text": "null ratio", "evidence_refs": ["rca:null"]},
        "what_is_impacted": {"text": "x", "evidence_refs": ["lineage_ref"]},
        "who_acts_first": {"text": "y", "evidence_refs": ["owner_ref"]},
        "what_to_do_next": {"text": "z", "evidence_refs": ["policy_ref"]},
    },
    "delivery": {
        "delivery": type("X", (), {"primary_output": "local_mirror", "slack_status": "failed", "local_status": "rendered", "degraded_reason_codes": []})(),
        "slack_payload": {},
        "local_mirror_payload": {},
    },
    "rca": None,
    "scored_assets": [],
    "recommendation": None,
    "fallback_reason_codes": [],
}


def _fake_run_pipeline(raw_event, om_data, slack_sender, mirror_writer=None):
    brief = dict(SAMPLE_PIPELINE_RESULT["brief"])
    brief["incident_id"] = raw_event["incident_id"]
    return {**SAMPLE_PIPELINE_RESULT, "brief": brief}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("OPENMETADATA_BASE_URL", raising=False)
    monkeypatch.setattr("incident_copilot.app.run_pipeline", _fake_run_pipeline)
    app = create_app()
    return TestClient(app)


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "has_openmetadata" in body
    assert "has_slack" in body


def test_metrics_endpoint_returns_counts(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.json()["incident_count"] == 0


def test_webhook_persists_incident(client):
    r = client.post("/webhooks/incidents", json={
        "entity": {
            "id": "tc-1",
            "fullyQualifiedName": "svc.db.orders",
            "testCaseResult": {"testCaseStatus": "Failed", "result": "null ratio"},
        }
    })
    assert r.status_code == 200
    body = r.json()
    assert "incident_id" in body
    assert body["brief"]["policy_state"] == "approval_required"


def test_list_returns_recent_incidents(client):
    client.post("/webhooks/incidents", json={
        "entity": {"id": "tc-1", "fullyQualifiedName": "a.b.c",
                   "testCaseResult": {"testCaseStatus": "Failed", "result": "x"}}
    })
    r = client.get("/incidents")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert len(body["items"]) >= 1


def test_fetch_by_id(client):
    post = client.post("/webhooks/incidents", json={
        "entity": {"id": "tc-1", "fullyQualifiedName": "a.b.c",
                   "testCaseResult": {"testCaseStatus": "Failed", "result": "x"}}
    })
    incident_id = post.json()["incident_id"]
    r = client.get(f"/incidents/{incident_id}")
    assert r.status_code == 200
    assert r.json()["incident_id"] == incident_id


def test_fetch_missing_returns_404(client):
    r = client.get("/incidents/does-not-exist")
    assert r.status_code == 404


def test_webhook_renders_html(client):
    post = client.post("/webhooks/incidents", json={
        "entity": {"id": "tc-1", "fullyQualifiedName": "a.b.c",
                   "testCaseResult": {"testCaseStatus": "Failed", "result": "x"}}
    })
    incident_id = post.json()["incident_id"]
    r = client.get(f"/incidents/{incident_id}/view")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert incident_id in r.text


def test_direct_canonical_envelope_passthrough(client):
    r = client.post("/webhooks/incidents", json={
        "incident_id": "canonical-1",
        "entity_fqn": "svc.db.x",
        "test_case_id": "tc-x",
        "severity": "high",
        "occurred_at": "2026-04-18T00:00:00Z",
        "raw_ref": "x",
    })
    assert r.status_code == 200
    assert r.json()["incident_id"] == "canonical-1"
