"""Tests for suggest_tests_for_table MCP tool."""
import pytest

from incident_copilot.mcp_facade import (
    _rule_based_suggestions,
    suggest_tests_for_table_tool,
)


def test_rule_based_always_includes_table_row_count():
    suggestions = _rule_based_suggestions("svc.db.orders", [])
    names = [s["test_name"] for s in suggestions]
    assert "tableRowCountToBeBetween" in names


def test_rule_based_id_column_gets_not_null_and_unique():
    columns = [{"name": "order_id", "dataType": "BIGINT"}]
    suggestions = _rule_based_suggestions("svc.db.orders", columns)
    col_tests = [s for s in suggestions if s.get("column") == "order_id"]
    test_names = [s["test_name"] for s in col_tests]
    assert "columnValuesToBeNotNull" in test_names
    assert "columnValuesToBeUnique" in test_names


def test_rule_based_email_column_gets_regex():
    columns = [{"name": "email_address", "dataType": "VARCHAR"}]
    suggestions = _rule_based_suggestions("svc.db.users", columns)
    email_tests = [s for s in suggestions if s.get("column") == "email_address"]
    assert any(s["test_name"] == "columnValuesToMatchRegex" for s in email_tests)
    regex_tests = [s for s in email_tests if s["test_name"] == "columnValuesToMatchRegex"]
    assert regex_tests[0]["params"].get("regex")


def test_rule_based_numeric_amount_column_gets_between():
    columns = [{"name": "total_amount", "dataType": "DECIMAL"}]
    suggestions = _rule_based_suggestions("svc.db.orders", columns)
    col_tests = [s for s in suggestions if s.get("column") == "total_amount"]
    assert any(s["test_name"] == "columnValuesToBeBetween" for s in col_tests)
    between = next(s for s in col_tests if s["test_name"] == "columnValuesToBeBetween")
    assert between["params"].get("minValue") == 0


def test_rule_based_status_string_column_gets_not_null():
    columns = [{"name": "order_status", "dataType": "STRING"}]
    suggestions = _rule_based_suggestions("svc.db.orders", columns)
    col_tests = [s for s in suggestions if s.get("column") == "order_status"]
    assert any(s["test_name"] == "columnValuesToBeNotNull" for s in col_tests)


def test_suggest_tests_tool_returns_expected_shape(monkeypatch):
    monkeypatch.delenv("OPENMETADATA_BASE_URL", raising=False)
    monkeypatch.delenv("OPENMETADATA_JWT_TOKEN", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    result = suggest_tests_for_table_tool("svc.db.orders")

    assert result["entity_fqn"] == "svc.db.orders"
    assert isinstance(result["suggestions"], list)
    assert len(result["suggestions"]) >= 1
    assert result["source"] == "rule_based"
    assert result["om_reachable"] is False


def test_suggest_tests_tool_uses_om_columns_when_available(monkeypatch):
    fake_columns = [
        {"name": "user_id", "dataType": "BIGINT"},
        {"name": "email", "dataType": "VARCHAR"},
        {"name": "revenue_usd", "dataType": "DECIMAL"},
    ]

    class FakeOMClient:
        @classmethod
        def from_env(cls):
            return cls()

        def fetch_table_metadata(self, fqn):
            return {"columns": fake_columns}

    monkeypatch.setattr("incident_copilot.openmetadata_client.OpenMetadataClient", FakeOMClient)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    result = suggest_tests_for_table_tool("svc.db.users")
    assert result["column_count"] == 3
    assert result["om_reachable"] is True
    suggestions = result["suggestions"]
    col_names = [s.get("column") for s in suggestions]
    assert "user_id" in col_names or "email" in col_names


def test_suggest_tests_tool_uses_ai_when_available(monkeypatch):
    fake_columns = [{"name": "id", "dataType": "INT"}]
    ai_suggestions = [
        {"test_name": "columnValuesToBeUnique", "column": "id", "params": {}, "rationale": "AI says unique."}
    ]

    class FakeOMClient:
        @classmethod
        def from_env(cls):
            return cls()

        def fetch_table_metadata(self, fqn):
            return {"columns": fake_columns}

    monkeypatch.setattr("incident_copilot.openmetadata_client.OpenMetadataClient", FakeOMClient)
    monkeypatch.setattr("incident_copilot.mcp_facade._ai_test_suggestions", lambda fqn, cols: ai_suggestions)

    result = suggest_tests_for_table_tool("svc.db.table")
    assert result["source"] == "ai"
    assert result["suggestions"] == ai_suggestions


def test_suggest_tests_tool_falls_back_to_rules_when_ai_returns_none(monkeypatch):
    class FakeOMClient:
        @classmethod
        def from_env(cls):
            return cls()

        def fetch_table_metadata(self, fqn):
            return {"columns": []}

    monkeypatch.setattr("incident_copilot.mcp_facade.OpenMetadataClient", FakeOMClient, raising=False)
    monkeypatch.setattr("incident_copilot.mcp_facade._ai_test_suggestions", lambda fqn, cols: None)

    result = suggest_tests_for_table_tool("svc.db.table")
    assert result["source"] == "rule_based"
    assert len(result["suggestions"]) >= 1


def test_suggest_tests_mcp_tool_is_callable():
    from incident_copilot.mcp_facade import suggest_tests_for_table
    result = suggest_tests_for_table("svc.db.orders")
    assert "suggestions" in result
    assert "entity_fqn" in result
