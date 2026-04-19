from incident_copilot.adapter import normalize_event


def test_adapter_handles_missing_fields_gracefully():
    out = normalize_event({"incident_id": "inc-1"})
    assert "MISSING_EVENT_FIELDS" in out["fallback_reason_codes"]
