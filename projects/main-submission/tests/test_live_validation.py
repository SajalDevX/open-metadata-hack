import pytest

from incident_copilot.live_validation import (
    bootstrap_target_fqn,
    candidate_entity_fqns,
    is_openmetadata_context_degraded,
    parse_table_fqn,
    require_live_openmetadata_resolution,
)


def test_candidate_entity_fqns_includes_service_prefixed_forms_for_three_part_fqn():
    out = candidate_entity_fqns("customer_analytics.raw.customer_profiles", ["demo_mysql", "backup_service"])
    assert out == [
        "customer_analytics.raw.customer_profiles",
        "demo_mysql.customer_analytics.raw.customer_profiles",
        "backup_service.customer_analytics.raw.customer_profiles",
    ]


def test_candidate_entity_fqns_keeps_four_part_fqn_only():
    out = candidate_entity_fqns("demo_mysql.customer_analytics.raw.customer_profiles", ["demo_mysql"])
    assert out == ["demo_mysql.customer_analytics.raw.customer_profiles"]


def test_is_openmetadata_context_degraded_detects_om_fallback_codes():
    codes = ["SLACK_SEND_FAILED", "OM_HTTP_FALLBACK_TO_FIXTURE"]
    assert is_openmetadata_context_degraded(codes) is True


def test_require_live_openmetadata_resolution_raises_for_degraded_om_context():
    with pytest.raises(RuntimeError):
        require_live_openmetadata_resolution(["MISSING_OWNER_METADATA", "SLACK_SEND_FAILED"])


def test_require_live_openmetadata_resolution_allows_non_om_degradation_only():
    require_live_openmetadata_resolution(["SLACK_SEND_FAILED"])


def test_parse_table_fqn_extracts_all_parts():
    assert parse_table_fqn("demo_mysql.customer_analytics.raw.customer_profiles") == (
        "demo_mysql",
        "customer_analytics",
        "raw",
        "customer_profiles",
    )


def test_parse_table_fqn_rejects_three_part_fqn():
    with pytest.raises(ValueError):
        parse_table_fqn("customer_analytics.raw.customer_profiles")


def test_bootstrap_target_fqn_prefers_first_service_hint_for_three_part_fqn():
    out = bootstrap_target_fqn("customer_analytics.raw.customer_profiles", ["demo_mysql", "secondary"])
    assert out == "demo_mysql.customer_analytics.raw.customer_profiles"
