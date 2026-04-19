import hashlib
import json
from dataclasses import asdict, is_dataclass

from fastmcp import FastMCP

from incident_copilot.context_resolver import resolve_context
from incident_copilot.impact import select_top_impacted_assets
from incident_copilot.impact_scorer import score_assets
from incident_copilot.rca_engine import build_rca
from incident_copilot.slack_sender import build_slack_sender

mcp = FastMCP("incident-copilot")


def _serialize_scored_asset(asset) -> dict:
    if isinstance(asset, dict):
        return dict(asset)
    if is_dataclass(asset):
        return asdict(asset)
    payload = {}
    for key in ("fqn", "score", "score_reason", "classifications", "business_facing", "distance"):
        if hasattr(asset, key):
            payload[key] = getattr(asset, key)
    return payload


def get_rca_tool(test_case_id: str, signal_type: str = "unknown") -> dict:
    result = build_rca(
        failed_test={"message": signal_type, "testType": signal_type},
        entity_fqn=test_case_id,
        use_ai=False,
    )
    return {
        "cause_tree": result.cause_tree,
        "narrative": result.narrative,
        "narrative_source": result.narrative_source,
        "signal_type": result.signal_type,
    }


def score_impact_tool(entity_fqn: str, lineage_depth: int = 2) -> list[dict]:
    envelope = {
        "incident_id": f"impact-{entity_fqn}",
        "entity_fqn": entity_fqn,
        "test_case_id": f"tc-{entity_fqn}",
        "severity": "unknown",
        "occurred_at": "",
        "raw_ref": entity_fqn,
    }
    context = resolve_context(envelope, om_client_data=None, max_depth=lineage_depth)
    impacted_assets = select_top_impacted_assets(context["impacted_assets"], max_assets=3, max_depth=lineage_depth)
    scored_assets = score_assets(impacted_assets)
    return [_serialize_scored_asset(asset) for asset in scored_assets]


def notify_slack_tool(incident_id: str, brief: dict | None = None) -> dict:
    result = {
        "status": "not_configured",
        "incident_id": incident_id,
        "fallback": "local_mirror",
    }
    if brief is not None:
        canonical_brief = json.dumps(brief, sort_keys=True, separators=(",", ":"), default=str)
        result["brief"] = brief
        result["payload_hash"] = hashlib.sha256(canonical_brief.encode("utf-8")).hexdigest()

    slack_sender = build_slack_sender()
    if slack_sender is None:
        return result

    payload = {"channel": "slack", "incident_id": incident_id}
    if brief is not None:
        payload["brief"] = brief

    try:
        sent = bool(slack_sender(payload))
    except Exception:
        sent = False

    if sent:
        result["status"] = "sent"
        result.pop("fallback", None)
    else:
        result["status"] = "failed"
        result["fallback"] = "local_mirror"
    return result


@mcp.tool
def triage_incident(incident_id: str, entity_fqn: str) -> dict:
    """Run full incident triage pipeline and return the canonical triage envelope."""
    from incident_copilot.orchestrator import run_pipeline
    raw_event = {
        "incident_id": incident_id,
        "entity_fqn": entity_fqn,
        "test_case_id": f"tc-{incident_id}",
        "severity": "high",
        "occurred_at": "",
        "raw_ref": incident_id,
    }
    om_data = resolve_context(raw_event, om_client_data=None, max_depth=2)
    return run_pipeline(raw_event, om_data, slack_sender=lambda _: False)


@mcp.tool
def score_impact(entity_fqn: str, lineage_depth: int = 2) -> list[dict]:
    """Score impacted assets for a given entity FQN."""
    return score_impact_tool(entity_fqn, lineage_depth)


@mcp.tool
def get_rca(test_case_id: str, signal_type: str = "unknown") -> dict:
    """Get root cause analysis for a failed test case."""
    return get_rca_tool(test_case_id, signal_type)


@mcp.tool
def notify_slack(incident_id: str, brief: dict | None = None) -> dict:
    """Trigger Slack notification for an incident brief."""
    return notify_slack_tool(incident_id, brief=brief)


if __name__ == "__main__":
    mcp.run()
