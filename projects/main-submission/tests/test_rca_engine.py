import os
from unittest.mock import patch

from incident_copilot.rca_engine import infer_signal_type, build_rca


def test_infer_null_signal():
    assert infer_signal_type({"message": "null ratio exceeded 15%"}) == "null_ratio_exceeded"


def test_infer_format_signal():
    assert infer_signal_type({"message": "format mismatch detected"}) == "format_mismatch"


def test_infer_referential_signal():
    assert infer_signal_type({"message": "referential integrity broken"}) == "referential_break"


def test_infer_volume_signal():
    assert infer_signal_type({"message": "volume drop detected"}) == "volume_drop"


def test_infer_unknown_signal():
    assert infer_signal_type({"message": "something weird happened"}) == "unknown"


def test_build_rca_template_fallback_when_no_key():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("OPENROUTER_API_KEY", None)
        result = build_rca({"message": "null ratio exceeded 15%"}, "svc.db.orders")
        assert result.signal_type == "null_ratio_exceeded"
        assert result.cause_tree == ["data_completeness", "upstream_null_propagation"]
        assert result.narrative_source == "template"
        assert result.narrative != ""


def test_build_rca_cause_tree_for_unknown():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("OPENROUTER_API_KEY", None)
        result = build_rca({"message": "???"}, "svc.db.orders")
        assert result.signal_type == "unknown"
        assert "unclassified" in result.cause_tree


def test_build_rca_uses_claude_when_key_available():
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test"}):
        with patch("incident_copilot.rca_engine._claude_narrative", return_value="Claude says: null upstream.") as mock_claude:
            result = build_rca({"message": "null ratio exceeded"}, "svc.db.orders")
            mock_claude.assert_called_once()
            assert result.narrative == "Claude says: null upstream."
            assert result.narrative_source == "claude"


def test_build_rca_falls_back_to_template_when_claude_raises():
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test"}):
        with patch("incident_copilot.rca_engine._claude_narrative", side_effect=Exception("timeout")):
            result = build_rca({"message": "null ratio exceeded"}, "svc.db.orders")
            assert result.narrative_source == "template"
            assert result.narrative != ""


def test_build_rca_falls_back_when_claude_returns_blank():
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test"}):
        with patch("incident_copilot.rca_engine._claude_narrative", return_value="   "):
            result = build_rca({"message": "null ratio exceeded"}, "svc.db.orders")
            assert result.narrative_source == "template"
            assert result.narrative == "Null ratio exceeded threshold — likely caused by upstream null propagation."
