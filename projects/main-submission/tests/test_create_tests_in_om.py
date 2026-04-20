"""Tests for create_tests_in_om MCP tool."""
import pytest
from incident_copilot.mcp_facade import create_tests_in_om_tool


class _FakeClient:
    def __init__(self, *, defs=None, suite=None, created=None, create_raises=None):
        self._defs = defs or {}
        self._suite = suite
        self._created = created or {"id": "abc-123", "fullyQualifiedName": "svc.db.t.col_not_null"}
        self._create_raises = create_raises
        self.created_calls = []

    @classmethod
    def from_env(cls):
        return _instance

    def fetch_test_definitions(self):
        return self._defs

    def fetch_basic_test_suite(self, entity_fqn):
        return self._suite

    def create_test_case(self, **kwargs):
        self.created_calls.append(kwargs)
        if self._create_raises:
            raise self._create_raises
        return self._created


_instance: _FakeClient | None = None


def _patch(monkeypatch, client: _FakeClient):
    global _instance
    _instance = client
    monkeypatch.setattr("incident_copilot.openmetadata_client.OpenMetadataClient", _FakeClient)


def test_no_suite_returns_error(monkeypatch):
    c = _FakeClient(
        defs={"columnValuesToBeNotNull": "def-uuid-1"},
        suite=None,
    )
    _patch(monkeypatch, c)
    result = create_tests_in_om_tool("svc.db.t", [{"test_name": "columnValuesToBeNotNull", "column": "col", "params": {}}])
    assert result["om_reachable"] is True
    assert result["created"] == []
    assert any("No basic test suite" in e for e in result["errors"])


def test_unknown_definition_is_skipped(monkeypatch):
    c = _FakeClient(defs={}, suite={"id": "suite-1"})
    _patch(monkeypatch, c)
    result = create_tests_in_om_tool(
        "svc.db.t",
        [{"test_name": "unknownTest", "column": None, "params": {}}],
    )
    assert result["created"] == []
    assert result["skipped"][0]["test_name"] == "unknownTest"
    assert result["skipped"][0]["reason"] == "unknown test definition"


def test_successful_column_test_creation(monkeypatch):
    c = _FakeClient(
        defs={"columnValuesToBeNotNull": "def-uuid-1"},
        suite={"id": "suite-uuid-1"},
        created={"id": "tc-1", "fullyQualifiedName": "svc.db.t.email_not_null"},
    )
    _patch(monkeypatch, c)
    result = create_tests_in_om_tool(
        "svc.db.t",
        [{"test_name": "columnValuesToBeNotNull", "column": "email", "params": {}}],
    )
    assert result["om_reachable"] is True
    assert len(result["created"]) == 1
    assert result["created"][0]["om_id"] == "tc-1"
    assert result["errors"] == []


def test_successful_table_level_test(monkeypatch):
    c = _FakeClient(
        defs={"tableRowCountToBeBetween": "def-row-1"},
        suite={"id": "suite-uuid-1"},
        created={"id": "tc-2", "fullyQualifiedName": "svc.db.t.table_row_count_between"},
    )
    _patch(monkeypatch, c)
    result = create_tests_in_om_tool(
        "svc.db.t",
        [{"test_name": "tableRowCountToBeBetween", "column": None, "params": {"minValue": 1}}],
    )
    assert len(result["created"]) == 1
    assert result["created"][0]["fqn"] == "svc.db.t.table_row_count_between"


def test_create_failure_recorded_in_errors(monkeypatch):
    c = _FakeClient(
        defs={"columnValuesToBeUnique": "def-uuid-2"},
        suite={"id": "suite-1"},
        create_raises=RuntimeError("OM rejected duplicate"),
    )
    _patch(monkeypatch, c)
    result = create_tests_in_om_tool(
        "svc.db.t",
        [{"test_name": "columnValuesToBeUnique", "column": "order_id", "params": {}}],
    )
    assert result["created"] == []
    assert any("OM rejected duplicate" in e.get("error", "") for e in result["errors"])


def test_om_unreachable_returns_error(monkeypatch):
    def bad_from_env():
        raise RuntimeError("connection refused")
    monkeypatch.setattr("incident_copilot.openmetadata_client.OpenMetadataClient.from_env", staticmethod(bad_from_env))
    result = create_tests_in_om_tool("svc.db.t", [])
    assert result["om_reachable"] is False
    assert len(result["errors"]) > 0


def test_multiple_suggestions_mixed_results(monkeypatch):
    c = _FakeClient(
        defs={"columnValuesToBeNotNull": "def-1", "columnValuesToBeUnique": "def-2"},
        suite={"id": "suite-1"},
        created={"id": "tc-ok", "fullyQualifiedName": "svc.db.t.col_not_null"},
    )
    _patch(monkeypatch, c)
    suggestions = [
        {"test_name": "columnValuesToBeNotNull", "column": "col", "params": {}},
        {"test_name": "unknownDef", "column": "col", "params": {}},
        {"test_name": "columnValuesToBeUnique", "column": "col", "params": {}},
    ]
    result = create_tests_in_om_tool("svc.db.t", suggestions)
    assert len(result["created"]) == 2
    assert len(result["skipped"]) == 1
    assert result["errors"] == []
