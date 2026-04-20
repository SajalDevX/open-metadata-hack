import hashlib
import json
import os
from dataclasses import asdict, is_dataclass

from fastmcp import FastMCP

from incident_copilot.context_resolver import resolve_context
from incident_copilot.impact import select_top_impacted_assets
from incident_copilot.impact_scorer import score_assets
from incident_copilot.openrouter_client import get_client, is_available
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


_NUMERIC_TYPES = {"INT", "BIGINT", "INTEGER", "SMALLINT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC", "NUMBER"}
_STRING_TYPES = {"STRING", "VARCHAR", "TEXT", "CHAR", "NVARCHAR"}


def _rule_based_suggestions(entity_fqn: str, columns: list[dict]) -> list[dict]:
    suggestions: list[dict] = [
        {
            "test_name": "tableRowCountToBeBetween",
            "column": None,
            "params": {"minValue": 1},
            "rationale": "Table should not be empty.",
        }
    ]
    for col in columns[:30]:
        name = col.get("name") or ""
        dtype = (col.get("dataType") or "").upper()
        name_lower = name.lower()

        if any(kw in name_lower for kw in ("_id", "id_", "_key", "uuid")):
            suggestions.append({
                "test_name": "columnValuesToBeNotNull",
                "column": name,
                "params": {},
                "rationale": f"ID/key column '{name}' must not contain nulls.",
            })
            suggestions.append({
                "test_name": "columnValuesToBeUnique",
                "column": name,
                "params": {},
                "rationale": f"ID/key column '{name}' should have no duplicates.",
            })

        elif dtype in _NUMERIC_TYPES and any(kw in name_lower for kw in ("amount", "count", "price", "revenue", "qty", "quantity")):
            suggestions.append({
                "test_name": "columnValuesToBeBetween",
                "column": name,
                "params": {"minValue": 0},
                "rationale": f"Numeric metric column '{name}' should be non-negative.",
            })

        elif "email" in name_lower:
            suggestions.append({
                "test_name": "columnValuesToMatchRegex",
                "column": name,
                "params": {"regex": "^[a-zA-Z0-9._%+\\-]+@[a-zA-Z0-9.\\-]+\\.[a-zA-Z]{2,}$"},
                "rationale": f"Email column '{name}' should match a valid email format.",
            })

        elif dtype in _STRING_TYPES and any(kw in name_lower for kw in ("status", "state", "type")):
            suggestions.append({
                "test_name": "columnValuesToBeNotNull",
                "column": name,
                "params": {},
                "rationale": f"Status/type column '{name}' should not be null.",
            })

    return suggestions


def _ai_test_suggestions(entity_fqn: str, columns: list[dict]) -> list[dict] | None:
    if not is_available():
        return None
    col_summary = "\n".join(
        f"- {c.get('name','?')} ({c.get('dataType','?')}): {c.get('description') or 'no description'}"
        for c in columns[:20]
    )
    prompt = (
        f"You are a data quality expert. Analyze these columns from OpenMetadata table `{entity_fqn}` "
        "and suggest 5-8 specific data quality tests.\n\n"
        f"Columns:\n{col_summary}\n\n"
        "For each test return a JSON object with keys:\n"
        '- "test_name": OpenMetadata test template name (e.g. tableRowCountToBeBetween, '
        "columnValuesToBeNotNull, columnValuesToBeUnique, columnValuesToBeBetween, "
        "columnValuesToMatchRegex, columnValueNullCount)\n"
        '- "column": column name (null for table-level tests)\n'
        '- "params": test parameters as object\n'
        '- "rationale": one sentence explaining why\n\n'
        "Return ONLY a valid JSON array. No markdown, no extra text."
    )
    try:
        client = get_client()
        response = client.chat.completions.create(
            model=os.environ.get("OPENROUTER_MODEL", "anthropic/claude-haiku-4-5"),
            messages=[{"role": "user", "content": prompt}],
            timeout=5.0,
        )
        text = (response.choices[0].message.content or "").strip()
        return json.loads(text)
    except Exception:
        return None


def suggest_tests_for_table_tool(entity_fqn: str) -> dict:
    columns: list[dict] = []
    om_reachable = False
    try:
        from incident_copilot.openmetadata_client import OpenMetadataClient
        client = OpenMetadataClient.from_env()
        table_data = client.fetch_table_metadata(entity_fqn)
        columns = table_data.get("columns") or []
        om_reachable = True
    except Exception:
        pass

    ai_suggestions = _ai_test_suggestions(entity_fqn, columns) if columns else None
    suggestions = ai_suggestions if ai_suggestions else _rule_based_suggestions(entity_fqn, columns)

    return {
        "entity_fqn": entity_fqn,
        "column_count": len(columns),
        "om_reachable": om_reachable,
        "source": "ai" if ai_suggestions else "rule_based",
        "suggestions": suggestions,
    }


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
    return run_pipeline(raw_event, None, slack_sender=lambda _: False)


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


@mcp.tool
def suggest_tests_for_table(entity_fqn: str) -> dict:
    """Analyze a table's schema and suggest data quality tests to add in OpenMetadata."""
    return suggest_tests_for_table_tool(entity_fqn)


if __name__ == "__main__":
    mcp.run()
