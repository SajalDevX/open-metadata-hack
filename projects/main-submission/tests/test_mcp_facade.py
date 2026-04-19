import hashlib
import json
from types import SimpleNamespace

from incident_copilot.mcp_facade import (
    get_rca,
    get_rca_tool,
    notify_slack,
    notify_slack_tool,
    score_impact,
    score_impact_tool,
    triage_incident,
)
from incident_copilot.orchestrator import run_pipeline


def test_get_rca_returns_cause_tree_and_narrative():
    result = get_rca_tool(test_case_id="tc-null-1", signal_type="null_ratio_exceeded")
    assert "cause_tree" in result
    assert result["cause_tree"] == ["data_completeness", "upstream_null_propagation"]
    assert result["narrative"] != ""
    assert result["signal_type"] == "null_ratio_exceeded"


def test_get_rca_unknown_signal():
    result = get_rca_tool(test_case_id="tc-unknown", signal_type="unknown")
    assert "unclassified" in result["cause_tree"]


def test_score_impact_returns_list():
    result = score_impact_tool(entity_fqn="svc.db.orders", lineage_depth=2)
    assert isinstance(result, list)


def test_score_impact_uses_pipeline_scoring_path(monkeypatch):
    calls = []

    def fake_resolve_context(envelope, om_client_data=None, max_depth=2):
        calls.append(("resolve_context", envelope, om_client_data, max_depth))
        return {
            "incident_id": envelope["incident_id"],
            "failed_test": {"message": "fixture"},
            "impacted_assets": [
                {
                    "fqn": "svc.db.orders",
                    "distance": 1,
                    "business_facing": True,
                    "downstream_count": 3,
                    "classifications": ["PII.Sensitive"],
                }
            ],
            "owners": {},
            "classifications": {},
            "fallback_reason_codes": [],
        }

    def fake_select_top_impacted_assets(assets, max_assets=3, max_depth=2):
        calls.append(("select_top_impacted_assets", assets, max_assets, max_depth))
        return assets

    def fake_score_assets(assets):
        calls.append(("score_assets", assets))
        return [
            SimpleNamespace(
                fqn="svc.db.orders",
                score=4.25,
                score_reason="business-facing +3.0, distance=1 +1.0, downstream=3 +2.0, → 6.0",
                classifications=["PII.Sensitive"],
                business_facing=True,
                distance=1,
            )
        ]

    monkeypatch.setattr("incident_copilot.mcp_facade.resolve_context", fake_resolve_context, raising=False)
    monkeypatch.setattr("incident_copilot.mcp_facade.select_top_impacted_assets", fake_select_top_impacted_assets, raising=False)
    monkeypatch.setattr("incident_copilot.mcp_facade.score_assets", fake_score_assets, raising=False)

    result = score_impact_tool(entity_fqn="svc.db.orders", lineage_depth=2)

    assert [call[0] for call in calls] == ["resolve_context", "select_top_impacted_assets", "score_assets"]
    assert result == [
        {
            "fqn": "svc.db.orders",
            "score": 4.25,
            "score_reason": "business-facing +3.0, distance=1 +1.0, downstream=3 +2.0, → 6.0",
            "classifications": ["PII.Sensitive"],
            "business_facing": True,
            "distance": 1,
        }
    ]


def test_triage_incident_returns_canonical_envelope_and_matches_pipeline_core_fields(monkeypatch):
    incident_id = "inc-input-42"
    entity_fqn = "svc.db.synthetic_orders"
    expected_event = {
        "incident_id": incident_id,
        "entity_fqn": entity_fqn,
        "test_case_id": f"tc-{incident_id}",
        "severity": "high",
        "occurred_at": "",
        "raw_ref": incident_id,
    }
    context = {
        "incident_id": incident_id,
        "failed_test": {"id": "tc-synthetic", "message": "null_ratio_exceeded", "threshold": 0.01, "observedValue": 0.2},
        "impacted_assets": [
            {"fqn": "svc.db.synthetic_orders", "distance": 1, "business_facing": True, "downstream_count": 2}
        ],
        "owners": {"svc.db.synthetic_orders": "team:data-eng"},
        "classifications": {"svc.db.synthetic_orders": ["PII.Sensitive"]},
        "fallback_reason_codes": [],
    }
    calls = []

    def fake_resolve_context(envelope, om_client_data=None, max_depth=2):
        calls.append((envelope, om_client_data, max_depth))
        return context

    monkeypatch.setattr("incident_copilot.mcp_facade.resolve_context", fake_resolve_context, raising=False)

    expected = run_pipeline(expected_event, context, slack_sender=lambda _brief: False)
    result = triage_incident(incident_id, entity_fqn)

    assert "brief" in result
    assert "delivery" in result
    assert calls == [(expected_event, None, 2)]
    for key in ["incident_id", "what_failed", "what_is_impacted", "who_acts_first", "what_to_do_next", "policy_state"]:
        assert result["brief"][key] == expected["brief"][key]
    assert result["delivery"]["delivery"].primary_output == expected["delivery"]["delivery"].primary_output


def test_notify_slack_returns_canonical_payload_hash():
    brief = {
        "incident_id": "inc-1",
        "policy_state": "approval_required",
        "what_failed": {"text": "x", "evidence_refs": ["incident_ref"]},
        "what_is_impacted": {"text": "y", "evidence_refs": ["lineage_ref"]},
        "who_acts_first": {"text": "z", "evidence_refs": ["owner_ref"]},
        "what_to_do_next": {"text": "n", "evidence_refs": ["policy_ref"]},
    }
    reordered = {
        "what_to_do_next": {"evidence_refs": ["policy_ref"], "text": "n"},
        "who_acts_first": {"evidence_refs": ["owner_ref"], "text": "z"},
        "incident_id": "inc-1",
        "what_failed": {"evidence_refs": ["incident_ref"], "text": "x"},
        "policy_state": "approval_required",
        "what_is_impacted": {"evidence_refs": ["lineage_ref"], "text": "y"},
    }

    result_a = notify_slack_tool(incident_id="inc-1", brief=brief)
    result_b = notify_slack_tool(incident_id="inc-1", brief=reordered)

    expected_hash = hashlib.sha256(
        json.dumps(brief, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()

    assert result_a["status"] == "not_configured"
    assert result_a["incident_id"] == "inc-1"
    assert result_a["fallback"] == "local_mirror"
    assert result_a["payload_hash"] == expected_hash
    assert result_b["payload_hash"] == expected_hash


def test_notify_slack_attempts_sender_when_configured(monkeypatch):
    brief = {
        "incident_id": "inc-2",
        "policy_state": "approval_required",
        "what_failed": {"text": "x", "evidence_refs": ["incident_ref"]},
    }
    sent_payloads = []

    def fake_build_slack_sender():
        def fake_sender(payload):
            sent_payloads.append(payload)
            return True

        return fake_sender

    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/services/T000/B000/TEST")
    monkeypatch.setattr("incident_copilot.mcp_facade.build_slack_sender", fake_build_slack_sender, raising=False)

    result = notify_slack_tool(incident_id="inc-2", brief=brief)

    assert result["status"] == "sent"
    assert result["incident_id"] == "inc-2"
    assert result["payload_hash"] == hashlib.sha256(
        json.dumps(brief, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    assert sent_payloads == [{"channel": "slack", "incident_id": "inc-2", "brief": brief}]


def test_notify_slack_preserves_not_configured_fallback(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK", raising=False)

    result = notify_slack_tool(incident_id="inc-1", brief={"incident_id": "inc-1"})

    assert result["status"] == "not_configured"
    assert result["fallback"] == "local_mirror"


def test_mcp_tools_are_callable():
    assert isinstance(get_rca("tc-null-1", "null_ratio_exceeded"), dict)
    assert isinstance(score_impact("svc.db.orders"), list)
    assert isinstance(notify_slack("inc-1"), dict)


def test_notify_slack_returns_status_dict():
    result = notify_slack_tool(incident_id="inc-1")
    assert "status" in result
    assert "incident_id" in result
    assert result["incident_id"] == "inc-1"
