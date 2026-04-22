from incident_copilot.webhook_parser import parse_om_alert_payload


def test_parse_test_case_result_alert():
    payload = {
        "eventType": "entityCreated",
        "entityType": "testCase",
        "entity": {
            "id": "tc-uuid-1",
            "name": "null_ratio_customer_id",
            # 5-part FQN: service.database.schema.table.testName — trim to table.
            "fullyQualifiedName": "svc.db.schema.customer_profiles.null_ratio_customer_id",
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
    assert event["entity_fqn"] == "svc.db.schema.customer_profiles"
    assert event["severity"] in {"high", "medium", "low", "unknown"}
    assert event["raw_ref"] == "tc-uuid-1"
    assert event["occurred_at"]


def test_direct_incident_payload_is_not_trusted_as_canonical():
    payload = {
        "incident_id": "inc-direct-1",
        "entity_fqn": "svc.db.orders",
        "test_case_id": "tc-42",
        "severity": "high",
        "occurred_at": "2026-04-18T00:00:00Z",
        "raw_ref": "direct",
    }
    event = parse_om_alert_payload(payload)
    assert event["incident_id"] != "inc-direct-1"
    assert event["raw_ref"] == ""


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


def test_entity_link_with_column_subpart_stops_at_columns():
    """Regression: OM test-case alerts include an entityLink like
    `<#E::table::fqn::columns::name>`. Our parser must return just the table FQN,
    not the full string with `::columns::name` appended.
    """
    payload = {
        "entity": {
            "id": "tc-3",
            "entityLink": "<#E::table::copilot_source_pg.customer_analytics.raw.users_profile::columns::full_name>",
            "testCaseResult": {"testCaseStatus": "Failed", "result": "x"},
        }
    }
    event = parse_om_alert_payload(payload)
    assert event["entity_fqn"] == "copilot_source_pg.customer_analytics.raw.users_profile"


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


def test_four_part_fqn_is_preserved_at_table_level():
    payload = {
        "entity": {
            "id": "tc-4",
            "fullyQualifiedName": "demo_mysql.customer_analytics.raw.customer_profiles",
            "testCaseResult": {"testCaseStatus": "Failed", "result": "x"},
        }
    }
    event = parse_om_alert_payload(payload)
    # Previously this was trimmed to 3 parts (schema-level) — now we keep the table.
    assert event["entity_fqn"] == "demo_mysql.customer_analytics.raw.customer_profiles"


def test_five_part_fqn_trims_to_table():
    payload = {
        "entity": {
            "id": "tc-5",
            "fullyQualifiedName": "demo_mysql.customer_analytics.raw.customer_profiles.customer_id",
            "testCaseResult": {"testCaseStatus": "Failed", "result": "x"},
        }
    }
    event = parse_om_alert_payload(payload)
    # Column-level FQN → resolve to its parent table.
    assert event["entity_fqn"] == "demo_mysql.customer_analytics.raw.customer_profiles"


def test_failed_test_carries_result_message():
    payload = {
        "entity": {
            "id": "tc-6",
            "fullyQualifiedName": "demo_mysql.customer_analytics.raw.customer_profiles",
            "testCaseResult": {
                "testCaseStatus": "Failed",
                "result": "null ratio on customer_id exceeded 15% threshold",
            },
            "testDefinition": {"name": "columnValueNullRatioExceeded"},
        }
    }
    event = parse_om_alert_payload(payload)
    assert event["failed_test"]["message"] == "null ratio on customer_id exceeded 15% threshold"
    assert event["failed_test"]["testType"] == "columnValueNullRatioExceeded"


def test_direct_incident_payload_does_not_carry_failed_test_passthrough():
    event = parse_om_alert_payload({
        "incident_id": "canon-1",
        "entity_fqn": "svc.db.schema.t",
        "test_case_id": "tc",
        "severity": "high",
        "occurred_at": "2026-04-18T00:00:00Z",
        "raw_ref": "x",
        "failed_test": {"message": "direct", "testType": "custom"},
    })
    assert event["failed_test"] == {}
