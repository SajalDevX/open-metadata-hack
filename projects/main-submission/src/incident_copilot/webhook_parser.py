"""Parse an OpenMetadata alert webhook payload into a canonical incident event envelope.

Supports:
- OpenMetadata `testCase` entityCreated/entityUpdated alert payloads (native format)
- Direct incident envelopes (already in canonical shape — pass-through)
- Partial/unknown payloads (fills with safe defaults, never raises)
"""
import re
import time
from datetime import datetime, timezone
from typing import Any


_ENTITY_LINK_RE = re.compile(r"<#E::[^:]+::([^>]+)>")


def _iso_from_millis(ms: Any) -> str:
    try:
        seconds = float(ms) / 1000.0
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return datetime.now(tz=timezone.utc).isoformat()


def _derive_entity_fqn(entity: dict) -> str:
    link = entity.get("entityLink")
    if isinstance(link, str):
        match = _ENTITY_LINK_RE.search(link)
        if match:
            return match.group(1)

    fqn = entity.get("fullyQualifiedName") or ""
    if fqn:
        parts = fqn.split(".")
        if len(parts) > 3:
            return ".".join(parts[:3])
        return fqn

    return ""


def _derive_severity(entity: dict) -> str:
    status = ((entity.get("testCaseResult") or {}).get("testCaseStatus") or "").lower()
    if status == "failed":
        return "high"
    if status == "aborted":
        return "medium"
    if status == "success":
        return "low"
    return "unknown"


def _is_canonical_envelope(payload: dict) -> bool:
    return all(k in payload for k in ("incident_id", "entity_fqn", "test_case_id"))


def parse_om_alert_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        payload = {}

    if _is_canonical_envelope(payload):
        return {
            "incident_id": payload["incident_id"],
            "entity_fqn": payload.get("entity_fqn", ""),
            "test_case_id": payload.get("test_case_id", ""),
            "severity": payload.get("severity", "unknown"),
            "occurred_at": payload.get("occurred_at", datetime.now(tz=timezone.utc).isoformat()),
            "raw_ref": payload.get("raw_ref", payload.get("incident_id", "")),
        }

    entity = payload.get("entity") or {}
    test_case_id = entity.get("id") or ""
    entity_fqn = _derive_entity_fqn(entity)
    severity = _derive_severity(entity)

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
    }
