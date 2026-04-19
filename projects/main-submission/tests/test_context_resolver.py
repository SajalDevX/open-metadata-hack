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
