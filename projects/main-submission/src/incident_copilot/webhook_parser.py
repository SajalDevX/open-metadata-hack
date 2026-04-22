"""Parse an OpenMetadata alert webhook payload into a canonical incident event envelope.

Supports:
- OpenMetadata `testCase` entityCreated/entityUpdated alert payloads (native format)
- Partial/unknown payloads (fills with safe defaults, never raises)
"""
import re
import time
from datetime import datetime, timezone
from typing import Any


# OpenMetadata entityLink format: `<#E::<type>::<fqn>[::<subpart>::<name>[::<subpart>::<name>]]>`
# We want the FQN, not any of the ::subpart:: suffixes that may trail it.
_ENTITY_LINK_RE = re.compile(r"<#E::[^:]+::((?:(?!::).)+?)(?:::|>)")


def _iso_from_millis(ms: Any) -> str:
    try:
        seconds = float(ms) / 1000.0
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return datetime.now(tz=timezone.utc).isoformat()


def _derive_entity_fqn(entity: dict) -> str:
    """Return the *table-level* FQN for the affected asset.

    OpenMetadata FQN depth conventions:
      3 parts → service.database.schema           (schema-level)
      4 parts → service.database.schema.table     (table-level)  ← preferred
      5 parts → service.database.schema.table.column (column-level)
      6 parts → test case FQN on a specific column

    When the payload points at a column or test case, we climb back up to the
    table so the pipeline can resolve lineage/ownership correctly.
    """
    link = entity.get("entityLink")
    if isinstance(link, str):
        match = _ENTITY_LINK_RE.search(link)
        if match:
            return match.group(1)

    fqn = entity.get("fullyQualifiedName") or ""
    if fqn:
        parts = fqn.split(".")
        # If 5+ parts, trim to table level (4 parts).
        if len(parts) >= 5:
            return ".".join(parts[:4])
        # 3 or 4 parts — return as-is (table or schema).
        return fqn

    return ""


def _extract_failed_test(entity: dict, payload: dict) -> dict:
    """Pull the failure signal out of an OM alert payload so downstream RCA
    doesn't have to re-query OpenMetadata. Returns {} if nothing usable found.
    """
    tcr = entity.get("testCaseResult") or {}
    message = tcr.get("result") or ""
    test_definition = entity.get("testDefinition") or {}
    test_type = (
        test_definition.get("name")
        if isinstance(test_definition, dict)
        else test_definition or ""
    ) or entity.get("name") or ""

    failed = {}
    if message:
        failed["message"] = message
    if test_type:
        failed["testType"] = test_type
    return failed


def _derive_severity(entity: dict) -> str:
    status = ((entity.get("testCaseResult") or {}).get("testCaseStatus") or "").lower()
    if status == "failed":
        return "high"
    if status == "aborted":
        return "medium"
    if status == "success":
        return "low"
    return "unknown"


def parse_om_alert_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        payload = {}

    entity = payload.get("entity") or {}
    test_case_id = entity.get("id") or ""
    entity_fqn = _derive_entity_fqn(entity)
    severity = _derive_severity(entity)
    failed_test = _extract_failed_test(entity, payload)

    timestamp = payload.get("timestamp")
    occurred_at = _iso_from_millis(timestamp) if timestamp else datetime.now(tz=timezone.utc).isoformat()

    incident_id = f"om-{test_case_id}-{int(time.time())}" if test_case_id else f"om-{int(time.time())}"

    return {
        "incident_id": incident_id,
        "entity_fqn": entity_fqn,
        "test_case_id": test_case_id,
        "severity": severity,
        "occurred_at": occurred_at,
        "raw_ref": test_case_id,
        "failed_test": failed_test,
    }
