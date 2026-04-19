from incident_copilot.adapter import normalize_event


def test_adapter_handles_missing_fields_gracefully():
    out = normalize_event({"incident_id": "inc-1"})
    assert "MISSING_EVENT_FIELDS" in out["fallback_reason_codes"]


def test_adapter_preserves_failed_test_from_webhook_payload():
    out = normalize_event({
        "incident_id": "inc-1",
        "entity_fqn": "a.b.c.d",
        "test_case_id": "tc",
        "severity": "high",
        "occurred_at": "x",
        "raw_ref": "x",
        "failed_test": {"message": "null ratio exceeded", "testType": "columnValueNullRatioExceeded"},
    })
    assert out["failed_test"]["message"] == "null ratio exceeded"
    assert out["failed_test"]["testType"] == "columnValueNullRatioExceeded"


def test_adapter_defaults_failed_test_to_empty_dict():
    out = normalize_event({"incident_id": "inc-1"})
    assert out["failed_test"] == {}
