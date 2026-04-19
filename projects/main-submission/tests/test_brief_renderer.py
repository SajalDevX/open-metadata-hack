from incident_copilot.brief_renderer import render_brief_html


SAMPLE_BRIEF = {
    "incident_id": "inc-replay-demo",
    "policy_state": "approval_required",
    "what_failed": {
        "text": "Null ratio on customer_id exceeded 15%.",
        "evidence_refs": ["incident_ref", "test_ref", "rca:null_ratio_exceeded"],
    },
    "what_is_impacted": {
        "text": "customer_curated (score:5.0), customer_dashboard (score:4.5)",
        "evidence_refs": ["lineage_ref", "score:customer_curated", "score:customer_dashboard"],
    },
    "who_acts_first": {
        "text": "dre-oncall via asset_owner",
        "evidence_refs": ["owner_ref"],
    },
    "what_to_do_next": {
        "text": "• Escalate to data steward\n• Do not process downstream",
        "evidence_refs": ["policy_ref", "classification_ref"],
    },
}


def test_render_contains_incident_id():
    html = render_brief_html(SAMPLE_BRIEF)
    assert "inc-replay-demo" in html


def test_render_contains_all_four_blocks():
    html = render_brief_html(SAMPLE_BRIEF)
    assert "What failed" in html
    assert "What is impacted" in html
    assert "Who acts first" in html
    assert "What to do next" in html


def test_render_shows_policy_state_badge():
    html = render_brief_html(SAMPLE_BRIEF)
    assert "approval_required" in html


def test_render_includes_evidence_refs():
    html = render_brief_html(SAMPLE_BRIEF)
    assert "rca:null_ratio_exceeded" in html
    assert "owner_ref" in html


def test_render_preserves_bullets_in_next_steps():
    html = render_brief_html(SAMPLE_BRIEF)
    assert "Escalate to data steward" in html
    assert "Do not process downstream" in html


def test_render_allowed_policy_shows_different_badge():
    brief = dict(SAMPLE_BRIEF, policy_state="allowed")
    html = render_brief_html(brief)
    assert ">allowed<" in html.lower() or "allowed</" in html.lower() or "allowed" in html


def test_render_is_self_contained_html():
    html = render_brief_html(SAMPLE_BRIEF)
    assert html.strip().startswith("<!doctype html>") or html.strip().startswith("<!DOCTYPE html>")
    assert "<style>" in html
    assert "</html>" in html
