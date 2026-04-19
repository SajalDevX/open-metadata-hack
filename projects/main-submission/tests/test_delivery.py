import json
from incident_copilot.delivery import deliver


def test_local_mirror_becomes_primary_when_slack_fails():
    brief = {"incident_id": "inc-1"}
    captured = {}

    def writer(payload):
        captured["payload"] = payload
        return "/tmp/latest_brief.json"

    out = deliver(
        brief,
        slack_sender=lambda _brief: False,
        mirror_writer=writer,
    )
    assert out["delivery"].primary_output == "local_mirror"
    assert "SLACK_SEND_FAILED" in (out["delivery"].degraded_reason_codes or [])
    assert out["local_mirror_payload"]["brief"]["incident_id"] == out["slack_payload"]["brief"]["incident_id"]
    assert captured["payload"]["brief"]["incident_id"] == out["local_mirror_payload"]["brief"]["incident_id"]


def test_delivery_parity_across_core_brief_fields():
    brief = {
        "incident_id": "inc-1",
        "what_failed": {"text": "x", "evidence_refs": ["incident_ref"]},
        "what_is_impacted": {"text": "y", "evidence_refs": ["lineage_ref"]},
        "who_acts_first": {"text": "z", "evidence_refs": ["owner_ref"]},
        "what_to_do_next": {"text": "n", "evidence_refs": ["policy_ref"]},
        "policy_state": "approval_required",
    }
    out = deliver(brief, slack_sender=lambda _brief: True, mirror_writer=lambda _payload: "/tmp/latest_brief.json")
    for key in ["incident_id", "what_failed", "what_is_impacted", "who_acts_first", "what_to_do_next", "policy_state"]:
        assert out["slack_payload"]["brief"][key] == out["local_mirror_payload"]["brief"][key]


def test_delivery_persists_local_mirror_artifact(tmp_path):
    mirror_path = tmp_path / "latest_brief.json"
    brief = {
        "incident_id": "inc-1",
        "what_failed": {"text": "x", "evidence_refs": ["incident_ref"]},
        "what_is_impacted": {"text": "y", "evidence_refs": ["lineage_ref"]},
        "who_acts_first": {"text": "z", "evidence_refs": ["owner_ref"]},
        "what_to_do_next": {"text": "n", "evidence_refs": ["policy_ref"]},
        "policy_state": "approval_required",
    }

    def writer(payload):
        mirror_path.write_text(json.dumps(payload), encoding="utf-8")
        return str(mirror_path)

    out = deliver(brief, slack_sender=lambda _brief: True, mirror_writer=writer)
    persisted = json.loads(mirror_path.read_text(encoding="utf-8"))
    assert persisted["brief"] == out["local_mirror_payload"]["brief"]
    for key in ["incident_id", "what_failed", "what_is_impacted", "who_acts_first", "what_to_do_next", "policy_state"]:
        assert persisted["brief"][key] == out["slack_payload"]["brief"][key]
