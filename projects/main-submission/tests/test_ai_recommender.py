import os
from unittest.mock import patch

from incident_copilot.contracts import PolicyDecision, ScoredAsset
from incident_copilot.ai_recommender import recommend

ALLOWED_POLICY = PolicyDecision(
    incident_id="inc-1", status="allowed", reason_codes=[], required_approver_role=None
)
APPROVAL_POLICY = PolicyDecision(
    incident_id="inc-1", status="approval_required",
    reason_codes=["PII_SENSITIVE_IMPACTED"], required_approver_role="data_steward"
)
TOP_ASSET = ScoredAsset(
    fqn="svc.db.orders", score=8.0,
    score_reason="business-facing +3.0 → 8.0",
    classifications=["PII.Sensitive"], business_facing=True, distance=1
)


def test_policy_fallback_when_no_key():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("OPENROUTER_API_KEY", None)
        result = recommend({"message": "null ratio exceeded"}, TOP_ASSET, ALLOWED_POLICY)
        assert result.source == "policy_fallback"
        assert len(result.bullets) >= 1


def test_approval_required_fallback_mentions_steward():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("OPENROUTER_API_KEY", None)
        result = recommend({"message": "null ratio exceeded"}, TOP_ASSET, APPROVAL_POLICY)
        assert result.source == "policy_fallback"
        assert any("steward" in b.lower() for b in result.bullets)


def test_uses_claude_when_key_available():
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test"}):
        with patch("incident_copilot.ai_recommender._claude_recommend", return_value=["Check upstream", "Notify owner"]):
            result = recommend({"message": "null ratio"}, TOP_ASSET, ALLOWED_POLICY)
            assert result.source == "claude"
            assert result.bullets == ["Check upstream", "Notify owner"]


def test_falls_back_when_claude_raises():
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test"}):
        with patch("incident_copilot.ai_recommender._claude_recommend", side_effect=Exception("timeout")):
            result = recommend({"message": "null ratio"}, TOP_ASSET, ALLOWED_POLICY)
            assert result.source == "policy_fallback"
            assert len(result.bullets) >= 1


def test_claude_empty_list_falls_back_to_policy():
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test"}):
        with patch("incident_copilot.ai_recommender._claude_recommend", return_value=[]):
            result = recommend({"message": "null ratio"}, TOP_ASSET, ALLOWED_POLICY)
            assert result.source == "policy_fallback"
            assert result.bullets == [
                "Proceed with manual remediation triage.",
                "Notify asset owner to investigate the root cause.",
            ]


def test_policy_fallback_when_no_asset():
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test"}):
        result = recommend({"message": "null ratio"}, None, ALLOWED_POLICY)
        assert result.source == "policy_fallback"
