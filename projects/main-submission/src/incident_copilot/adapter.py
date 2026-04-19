REQUIRED = ["incident_id", "entity_fqn", "test_case_id", "severity", "occurred_at", "raw_ref"]


def normalize_event(raw):
    missing = [k for k in REQUIRED if k not in raw]
    return {
        "incident_id": raw.get("incident_id", "unknown-incident"),
        "source": "openmetadata",
        "event_type": "dq_incident",
        "entity_fqn": raw.get("entity_fqn", ""),
        "test_case_id": raw.get("test_case_id", ""),
        "severity": raw.get("severity", "unknown"),
        "occurred_at": raw.get("occurred_at", ""),
        "raw_ref": raw.get("raw_ref", ""),
        # Preserve an inline failure signal when the webhook payload carries it
        # — used by Context Resolver as a fallback when OM lookup can't resolve
        # the test case (e.g. ad-hoc/demo events not yet in the OM catalog).
        "failed_test": raw.get("failed_test") or {},
        "fallback_reason_codes": ["MISSING_EVENT_FIELDS"] if missing else [],
    }
