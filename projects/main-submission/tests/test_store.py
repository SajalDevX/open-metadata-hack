import json

from incident_copilot.store import IncidentStore


SAMPLE_BRIEF = {
    "incident_id": "inc-1",
    "policy_state": "approval_required",
    "what_failed": {"text": "null ratio", "evidence_refs": ["rca:null"]},
    "what_is_impacted": {"text": "x", "evidence_refs": ["lineage_ref"]},
    "who_acts_first": {"text": "y", "evidence_refs": ["owner_ref"]},
    "what_to_do_next": {"text": "z", "evidence_refs": ["policy_ref"]},
}


def test_store_initializes_empty(tmp_path):
    store = IncidentStore(str(tmp_path / "db.sqlite"))
    assert store.list_recent(limit=10) == []


def test_save_and_fetch_brief(tmp_path):
    store = IncidentStore(str(tmp_path / "db.sqlite"))
    store.save_brief(SAMPLE_BRIEF, delivery_status="sent", primary_output="slack")
    rows = store.list_recent(limit=10)
    assert len(rows) == 1
    assert rows[0]["incident_id"] == "inc-1"
    assert rows[0]["policy_state"] == "approval_required"
    assert rows[0]["delivery_status"] == "sent"


def test_fetch_by_id_returns_full_brief(tmp_path):
    store = IncidentStore(str(tmp_path / "db.sqlite"))
    store.save_brief(SAMPLE_BRIEF, delivery_status="sent", primary_output="slack")
    row = store.fetch_by_id("inc-1")
    assert row is not None
    assert row["brief"]["what_failed"]["text"] == "null ratio"


def test_fetch_missing_returns_none(tmp_path):
    store = IncidentStore(str(tmp_path / "db.sqlite"))
    assert store.fetch_by_id("nope") is None


def test_same_incident_overwrites(tmp_path):
    store = IncidentStore(str(tmp_path / "db.sqlite"))
    store.save_brief(SAMPLE_BRIEF, delivery_status="sent", primary_output="slack")
    updated = dict(SAMPLE_BRIEF, policy_state="allowed")
    store.save_brief(updated, delivery_status="sent", primary_output="slack")
    row = store.fetch_by_id("inc-1")
    assert row["policy_state"] == "allowed"
    assert len(store.list_recent(limit=10)) == 1


def test_list_recent_ordered_by_time(tmp_path):
    store = IncidentStore(str(tmp_path / "db.sqlite"))
    store.save_brief(dict(SAMPLE_BRIEF, incident_id="inc-1"), delivery_status="sent", primary_output="slack")
    store.save_brief(dict(SAMPLE_BRIEF, incident_id="inc-2"), delivery_status="sent", primary_output="slack")
    rows = store.list_recent(limit=10)
    assert [r["incident_id"] for r in rows] == ["inc-2", "inc-1"]


def test_payload_hash_round_trip(tmp_path):
    store = IncidentStore(str(tmp_path / "db.sqlite"))
    store.save_brief(SAMPLE_BRIEF, delivery_status="sent", primary_output="slack", payload_hash="abc123")
    row = store.fetch_by_id("inc-1")
    assert row["payload_hash"] == "abc123"


def test_count_returns_total(tmp_path):
    store = IncidentStore(str(tmp_path / "db.sqlite"))
    store.save_brief(dict(SAMPLE_BRIEF, incident_id="a"), delivery_status="sent", primary_output="slack")
    store.save_brief(dict(SAMPLE_BRIEF, incident_id="b"), delivery_status="sent", primary_output="slack")
    assert store.count() == 2
