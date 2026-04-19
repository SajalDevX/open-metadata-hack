import os
from unittest.mock import patch

from incident_copilot.orchestrator import run_pipeline


def test_golden_path_returns_approval_required():
    raw = {
        "incident_id": "inc-1",
        "entity_fqn": "svc.db.customer_profiles",
        "test_case_id": "tc-1",
        "severity": "high",
        "occurred_at": "2026-04-18T00:00:00Z",
        "raw_ref": "evt-1",
    }
    om_data = {
        "failed_test": {"message": "null ratio high"},
        "lineage": [{"fqn": "svc.db.customer_curated", "distance": 1, "business_facing": True, "owner": "dre-oncall"}],
        "owners": {"asset_owner": "dre-oncall"},
        "classifications": {"svc.db.customer_curated": ["PII.Sensitive"]},
    }
    out = run_pipeline(raw, om_data, slack_sender=lambda _b: True)
    assert out["brief"]["policy_state"] == "approval_required"


def test_degraded_path_carries_reason_codes():
    out = run_pipeline(
        {"incident_id": "inc-1"},
        {"failed_test": {}, "lineage": [], "owners": {}, "classifications": {}},
        slack_sender=lambda _b: False,
    )
    assert out["delivery"]["delivery"].primary_output == "local_mirror"
    assert out["fallback_reason_codes"]


RAW = {
    "incident_id": "inc-1", "entity_fqn": "svc.db.customer_profiles",
    "test_case_id": "tc-1", "severity": "high",
    "occurred_at": "2026-04-18T00:00:00Z", "raw_ref": "evt-1",
}
OM_DATA = {
    "failed_test": {"message": "null ratio exceeded 15%"},
    "lineage": [{"fqn": "svc.db.customer_curated", "distance": 1, "business_facing": True,
                 "downstream_count": 3, "owner": "dre-oncall"}],
    "owners": {"asset_owner": "dre-oncall"},
    "classifications": {"svc.db.customer_curated": ["PII.Sensitive"]},
}


def test_pipeline_returns_rca_result():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("OPENROUTER_API_KEY", None)
        out = run_pipeline(RAW, OM_DATA, slack_sender=lambda _: True)
        assert "rca" in out
        assert out["rca"].signal_type == "null_ratio_exceeded"
        assert out["rca"].narrative != ""


def test_pipeline_returns_scored_assets():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("OPENROUTER_API_KEY", None)
        out = run_pipeline(RAW, OM_DATA, slack_sender=lambda _: True)
        assert "scored_assets" in out
        assert len(out["scored_assets"]) == 1
        assert out["scored_assets"][0].fqn == "svc.db.customer_curated"
        assert out["scored_assets"][0].score > 0


def test_pipeline_returns_recommendation():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("OPENROUTER_API_KEY", None)
        out = run_pipeline(RAW, OM_DATA, slack_sender=lambda _: True)
        assert "recommendation" in out
        assert len(out["recommendation"].bullets) >= 1


def test_brief_what_failed_contains_rca_narrative():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("OPENROUTER_API_KEY", None)
        out = run_pipeline(RAW, OM_DATA, slack_sender=lambda _: True)
        assert "null" in out["brief"]["what_failed"]["text"].lower()


def test_brief_what_is_impacted_contains_score():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("OPENROUTER_API_KEY", None)
        out = run_pipeline(RAW, OM_DATA, slack_sender=lambda _: True)
        assert "score:" in out["brief"]["what_is_impacted"]["text"]
