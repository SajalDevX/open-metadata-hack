import os
from unittest.mock import patch

from incident_copilot.context_resolver import resolve_context


def test_resolver_returns_required_context_sections():
    env = {"incident_id": "inc-1", "entity_fqn": "svc.db.customer_profiles"}
    fake_client = {
        "failed_test": {"name": "null_check", "message": "null ratio high"},
        "lineage": [{"fqn": "svc.db.customer_curated", "distance": 1}],
        "owners": {"asset_owner": "dre-oncall", "domain_owner": "domain-lead"},
        "classifications": {"svc.db.customer_curated": ["PII.Sensitive"]},
    }
    out = resolve_context(env, fake_client, max_depth=2)
    assert "failed_test" in out and "impacted_assets" in out and "fallback_reason_codes" in out
    assert out["impacted_assets"][0]["classifications"] == ["PII.Sensitive"]


def test_resolver_adds_reason_code_for_missing_owner():
    env = {"incident_id": "inc-1", "entity_fqn": "svc.db.customer_profiles"}
    fake_client = {"failed_test": {}, "lineage": [], "owners": {}, "classifications": {}}
    out = resolve_context(env, fake_client, max_depth=2)
    assert "MISSING_OWNER_METADATA" in out["fallback_reason_codes"]


def test_resolver_uses_classification_map_when_lineage_item_has_none():
    env = {"incident_id": "inc-1", "entity_fqn": "svc.db.customer_profiles"}
    fake_client = {
        "failed_test": {"message": "x"},
        "lineage": [{"fqn": "svc.db.customer_curated", "distance": 1}],
        "owners": {"asset_owner": "dre-oncall"},
        "classifications": {"svc.db.customer_curated": ["PII.Sensitive"]},
    }
    out = resolve_context(env, fake_client, max_depth=2)
    assert out["impacted_assets"][0]["classifications"] == ["PII.Sensitive"]


def test_http_mode_uses_live_resolver_payload():
    env = {"incident_id": "inc-1", "entity_fqn": "svc.db.customer_profiles", "test_case_id": "tc-1"}
    live_payload = {
        "failed_test": {"name": "tc-1", "message": "null ratio exceeded", "testType": "tableColumnCountToEqual"},
        "lineage": [{"fqn": "svc.db.customer_curated", "distance": 1, "classifications": ["PII.Sensitive"]}],
        "owners": {"asset_owner": "dre-oncall"},
        "classifications": {"svc.db.customer_curated": ["PII.Sensitive"]},
    }
    with patch.dict(os.environ, {"OM_CONTEXT_SOURCE": "direct_http"}, clear=False):
        with patch("incident_copilot.context_resolver._resolve_via_http", return_value=live_payload):
            out = resolve_context(env, om_client_data={}, max_depth=2)
    assert out["failed_test"]["name"] == "tc-1"
    assert out["impacted_assets"][0]["fqn"] == "svc.db.customer_curated"


def test_mcp_mode_falls_back_to_http():
    env = {"incident_id": "inc-1", "entity_fqn": "svc.db.customer_profiles", "test_case_id": "tc-1"}
    live_payload = {
        "failed_test": {"name": "tc-1", "message": "null ratio exceeded", "testType": "tableColumnCountToEqual"},
        "lineage": [],
        "owners": {"asset_owner": "dre-oncall"},
        "classifications": {},
    }
    with patch.dict(os.environ, {"USE_OM_MCP": "true"}, clear=False):
        with patch("incident_copilot.context_resolver._resolve_via_mcp", side_effect=RuntimeError("mcp unavailable")):
            with patch("incident_copilot.context_resolver._resolve_via_http", return_value=live_payload):
                out = resolve_context(env, om_client_data={}, max_depth=2)
    assert "OM_MCP_FALLBACK_TO_HTTP" in out["fallback_reason_codes"]
    assert out["failed_test"]["name"] == "tc-1"


def test_http_failure_falls_back_to_fixture_payload():
    env = {"incident_id": "inc-1", "entity_fqn": "svc.db.customer_profiles", "test_case_id": "tc-1"}
    fixture_payload = {
        "failed_test": {"name": "fixture", "message": "fixture fallback", "testType": "x"},
        "lineage": [],
        "owners": {},
        "classifications": {},
    }
    with patch.dict(os.environ, {"OM_CONTEXT_SOURCE": "direct_http"}, clear=False):
        with patch("incident_copilot.context_resolver._resolve_via_http", side_effect=Exception("http down")):
            out = resolve_context(env, om_client_data=fixture_payload, max_depth=2)
    assert "OM_HTTP_FALLBACK_TO_FIXTURE" in out["fallback_reason_codes"]
    assert out["failed_test"]["name"] == "fixture"
