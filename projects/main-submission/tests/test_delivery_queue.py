import time

from incident_copilot.delivery_queue import DeliveryQueue
from incident_copilot.store import IncidentStore


SAMPLE_BRIEF = {
    "incident_id": "inc-q-1",
    "policy_state": "allowed",
    "what_failed": {"text": "x", "evidence_refs": []},
    "what_is_impacted": {"text": "x", "evidence_refs": []},
    "who_acts_first": {"text": "x", "evidence_refs": []},
    "what_to_do_next": {"text": "x", "evidence_refs": []},
}


def _make(tmp_path):
    db = str(tmp_path / "db.sqlite")
    return IncidentStore(db), DeliveryQueue(db)


def test_enqueue_and_fetch_pending(tmp_path):
    store, queue = _make(tmp_path)
    store.save_brief(SAMPLE_BRIEF, delivery_status="failed", primary_output="local_mirror")
    queue.enqueue("inc-q-1", reason="SLACK_SEND_FAILED")
    pending = queue.pending(limit=10)
    assert len(pending) == 1
    assert pending[0]["incident_id"] == "inc-q-1"
    assert pending[0]["attempts"] == 0


def test_mark_success_removes_from_pending(tmp_path):
    store, queue = _make(tmp_path)
    store.save_brief(SAMPLE_BRIEF, delivery_status="failed", primary_output="local_mirror")
    queue.enqueue("inc-q-1", reason="SLACK_SEND_FAILED")
    queue.mark_success("inc-q-1")
    assert queue.pending() == []


def test_mark_failed_increments_attempts(tmp_path):
    store, queue = _make(tmp_path)
    store.save_brief(SAMPLE_BRIEF, delivery_status="failed", primary_output="local_mirror")
    queue.enqueue("inc-q-1", reason="SLACK_SEND_FAILED")
    queue.mark_failed("inc-q-1", last_error="timeout", backoff_seconds=0)
    pending = queue.pending()
    assert pending[0]["attempts"] == 1
    assert pending[0]["last_error"] == "timeout"


def test_max_attempts_filters_out_dead(tmp_path):
    store, queue = _make(tmp_path)
    store.save_brief(SAMPLE_BRIEF, delivery_status="failed", primary_output="local_mirror")
    queue.enqueue("inc-q-1", reason="SLACK_SEND_FAILED")
    for _ in range(5):
        queue.mark_failed("inc-q-1", last_error="x", backoff_seconds=0)
    assert queue.pending(max_attempts=5) == []


def test_pending_respects_not_before(tmp_path):
    store, queue = _make(tmp_path)
    store.save_brief(SAMPLE_BRIEF, delivery_status="failed", primary_output="local_mirror")
    queue.enqueue("inc-q-1", reason="SLACK_SEND_FAILED")
    queue.mark_failed("inc-q-1", last_error="x", backoff_seconds=60)
    # Just failed with 60s backoff — should not appear now
    assert queue.pending() == []
    # But with now-shifted logic, a past timestamp would return it
    pending_now = queue.pending(now=time.time() + 120)
    assert len(pending_now) == 1


def test_enqueue_is_idempotent(tmp_path):
    store, queue = _make(tmp_path)
    store.save_brief(SAMPLE_BRIEF, delivery_status="failed", primary_output="local_mirror")
    queue.enqueue("inc-q-1", reason="SLACK_SEND_FAILED")
    queue.enqueue("inc-q-1", reason="SLACK_SEND_FAILED")
    assert len(queue.pending()) == 1
