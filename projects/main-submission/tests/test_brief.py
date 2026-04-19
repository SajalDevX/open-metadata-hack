from incident_copilot.brief import build_incident_brief


def test_each_brief_block_has_evidence_refs():
    brief = build_incident_brief(
        incident_id="inc-1",
        what_failed=("Null ratio exceeded", ["incident_ref", "test_ref"]),
        what_is_impacted=("customer_curated, dashboard_x", ["lineage_ref"]),
        who_acts_first=("dre-oncall via asset_owner", ["owner_ref"]),
        what_to_do_next=("Escalate for steward approval", ["classification_ref", "policy_ref"]),
        policy_state="approval_required",
    )
    assert brief["what_failed"]["evidence_refs"]
    assert brief["what_is_impacted"]["evidence_refs"]
    assert brief["who_acts_first"]["evidence_refs"]
    assert brief["what_to_do_next"]["evidence_refs"]
