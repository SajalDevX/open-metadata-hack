from incident_copilot.terminal_renderer import render_brief_terminal


SAMPLE_BRIEF = {
    "incident_id": "inc-1",
    "policy_state": "approval_required",
    "what_failed": {
        "text": "Null ratio exceeded 15%.",
        "evidence_refs": ["rca:null_ratio_exceeded"],
    },
    "what_is_impacted": {
        "text": "svc.db.orders (score:5.0)",
        "evidence_refs": ["lineage_ref", "score:svc.db.orders"],
    },
    "who_acts_first": {"text": "dre-oncall via asset_owner", "evidence_refs": ["owner_ref"]},
    "what_to_do_next": {"text": "• Escalate to data steward", "evidence_refs": ["policy_ref"]},
}


def test_terminal_output_contains_incident_and_policy():
    out = render_brief_terminal(SAMPLE_BRIEF)
    assert "inc-1" in out
    assert "approval_required" in out.lower()


def test_terminal_output_contains_all_four_blocks():
    out = render_brief_terminal(SAMPLE_BRIEF)
    for label in ("WHAT FAILED", "WHAT IS IMPACTED", "WHO ACTS FIRST", "WHAT TO DO NEXT"):
        assert label in out


def test_terminal_output_contains_evidence_refs():
    out = render_brief_terminal(SAMPLE_BRIEF)
    assert "rca:null_ratio_exceeded" in out
    assert "owner_ref" in out


def test_terminal_no_color_mode_strips_ansi():
    colored = render_brief_terminal(SAMPLE_BRIEF, use_color=True)
    plain = render_brief_terminal(SAMPLE_BRIEF, use_color=False)
    assert "\x1b[" in colored
    assert "\x1b[" not in plain
