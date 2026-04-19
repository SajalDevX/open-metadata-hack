from incident_copilot.webhook_parser import parse_om_alert_payload


def test_parse_test_case_result_alert():
    payload = {
        "eventType": "entityCreated",
        "entityType": "testCase",
        "entity": {
            "id": "tc-uuid-1",
            "name": "null_ratio_customer_id",
            "fullyQualifiedName": "svc.db.customer_profiles.customer_id.null_ratio_customer_id",
            "testDefinition": {"name": "columnValueNullRatioExceeded"},
            "testCaseResult": {
                "testCaseStatus": "Failed",
                "result": "null ratio exceeded 15% threshold",
            },
        },
        "timestamp": 1713436800000,
    }
    event = parse_om_alert_payload(payload)
    assert event["incident_id"].startswith("om-")
    assert event["test_case_id"] == "tc-uuid-1"
    assert event["entity_fqn"] == "svc.db.customer_profiles"
    assert event["severity"] in {"high", "medium", "low", "unknown"}
    assert event["raw_ref"] == "tc-uuid-1"
    assert event["occurred_at"]


def test_parse_direct_incident_payload():
    payload = {
        "incident_id": "inc-direct-1",
        "entity_fqn": "svc.db.orders",
        "test_case_id": "tc-42",
        "severity": "high",
        "occurred_at": "2026-04-18T00:00:00Z",
        "raw_ref": "direct",
    }
    event = parse_om_alert_payload(payload)
    assert event["incident_id"] == "inc-direct-1"
    assert event["entity_fqn"] == "svc.db.orders"


def test_parse_falls_back_to_unknown_when_missing():
    event = parse_om_alert_payload({})
    assert event["incident_id"].startswith("om-")
    assert event["entity_fqn"] == ""
    assert event["test_case_id"] == ""


def test_derives_entity_fqn_from_nested_entity_link():
    payload = {
        "entityType": "testCase",
        "entity": {
            "id": "tc-2",
            "entityLink": "<#E::table::svc.db.orders>",
            "testCaseResult": {"testCaseStatus": "Failed", "result": "x"},
        },
    }
    event = parse_om_alert_payload(payload)
    assert event["entity_fqn"] == "svc.db.orders"


def test_severity_from_failed_status():
    payload = {
        "entity": {"id": "tc-3", "testCaseResult": {"testCaseStatus": "Failed", "result": "x"}}
    }
    event = parse_om_alert_payload(payload)
    assert event["severity"] == "high"


def test_severity_from_aborted_is_medium():
    payload = {
        "entity": {"id": "tc-3", "testCaseResult": {"testCaseStatus": "Aborted", "result": "x"}}
    }
    event = parse_om_alert_payload(payload)
    assert event["severity"] == "medium"
