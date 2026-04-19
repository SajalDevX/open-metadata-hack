from incident_copilot.contracts import RCAResult
from incident_copilot.openrouter_client import is_available, get_client

SIGNAL_MAP: dict[str, list[str]] = {
    "null_ratio_exceeded": ["data_completeness", "upstream_null_propagation"],
    "format_mismatch": ["data_conformity", "schema_drift"],
    "referential_break": ["data_integrity", "upstream_delete_cascade"],
    "volume_drop": ["data_freshness", "ingestion_lag"],
    "unknown": ["unclassified", "manual_investigation_required"],
}

TEMPLATE_NARRATIVES: dict[str, str] = {
    "null_ratio_exceeded": "Null ratio exceeded threshold — likely caused by upstream null propagation.",
    "format_mismatch": "Format mismatch detected — likely caused by schema drift in source data.",
    "referential_break": "Referential integrity broken — likely caused by upstream delete cascade.",
    "volume_drop": "Volume drop detected — likely caused by ingestion lag or pipeline failure.",
    "unknown": "Unclassified failure — manual investigation required.",
}


def infer_signal_type(failed_test: dict) -> str:
    msg = (failed_test.get("message") or "").lower()
    test_type = (failed_test.get("testType") or "").lower()
    combined = msg + " " + test_type
    if "null" in combined:
        return "null_ratio_exceeded"
    if "format" in combined:
        return "format_mismatch"
    if "referential" in combined or "foreign" in combined:
        return "referential_break"
    if "volume" in combined or "count" in combined:
        return "volume_drop"
    return "unknown"


def build_rca(failed_test: dict, entity_fqn: str, use_ai: bool = True) -> RCAResult:
    signal = infer_signal_type(failed_test)
    cause_tree = SIGNAL_MAP[signal]
    narrative = None
    source = "template"

    if use_ai and is_available():
        try:
            narrative = _claude_narrative(signal, cause_tree, failed_test, entity_fqn)
            if narrative.strip():
                source = "claude"
            else:
                narrative = None
        except Exception:
            pass

    if narrative is None:
        narrative = TEMPLATE_NARRATIVES[signal]

    return RCAResult(
        cause_tree=cause_tree,
        narrative=narrative,
        narrative_source=source,
        signal_type=signal,
    )


def _claude_narrative(signal: str, cause_tree: list[str], failed_test: dict, entity_fqn: str) -> str:
    client = get_client()
    prompt = (
        f"A data quality check failed on asset '{entity_fqn}'.\n"
        f"Test message: {failed_test.get('message', 'unknown')}\n"
        f"Root cause category: {' > '.join(cause_tree)}\n"
        f"Write 1-2 sentences explaining what failed and why, in plain English for a data engineer."
    )
    resp = client.chat.completions.create(
        model="anthropic/claude-haiku-4-5",
        max_tokens=128,
        timeout=3,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip()
