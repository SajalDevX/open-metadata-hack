"""Tests for new MCP tools: list_recent_failures, get_table_info."""
import pytest
from incident_copilot.mcp_facade import list_recent_failures, get_table_info


def test_list_recent_failures_returns_list(monkeypatch, tmp_path):
    db = str(tmp_path / "test.db")
    from incident_copilot.store import IncidentStore
    store = IncidentStore(db)
    store.save_brief(
        brief={
            "incident_id": "inc-mcp-1",
            "policy_state": "allowed",
            "what_failed": {"text": "Null ratio exceeded", "evidence_refs": ["rca:null_ratio_exceeded"]},
            "what_is_impacted": {"text": "svc.db.orders", "evidence_refs": []},
            "who_acts_first": {"text": "dre-oncall", "evidence_refs": []},
            "what_to_do_next": {"text": "investigate", "evidence_refs": []},
        },
        delivery_status="rendered",
        primary_output="local_mirror",
    )

    monkeypatch.setenv("COPILOT_DB_PATH", db)
    result = list_recent_failures(limit=5)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["incident_id"] == "inc-mcp-1"
    assert result[0]["policy_state"] == "allowed"
    assert "Null ratio exceeded" in result[0]["what_failed"]


def test_list_recent_failures_empty_store(monkeypatch, tmp_path):
    monkeypatch.setenv("COPILOT_DB_PATH", str(tmp_path / "empty.db"))
    result = list_recent_failures(limit=5)
    assert result == []


def test_get_table_info_om_not_reachable(monkeypatch):
    monkeypatch.delenv("OPENMETADATA_BASE_URL", raising=False)
    monkeypatch.delenv("OPENMETADATA_JWT_TOKEN", raising=False)
    result = get_table_info("svc.db.orders")
    assert result["entity_fqn"] == "svc.db.orders"
    assert result["om_reachable"] is False
    assert "error" in result


def test_get_table_info_returns_columns_when_om_available(monkeypatch):
    fake_table = {
        "name": "orders",
        "description": "Daily orders table",
        "owners": [{"name": "dre-oncall", "type": "user"}],
        "tags": [{"tagFQN": "PII.Sensitive"}],
        "columns": [
            {"name": "order_id", "dataType": "BIGINT", "description": "Primary key"},
            {"name": "total_amount", "dataType": "DECIMAL", "description": "Order total"},
        ],
    }

    class FakeOMClient:
        @classmethod
        def from_env(cls):
            return cls()

        def fetch_table_metadata(self, fqn):
            return fake_table

    monkeypatch.setattr("incident_copilot.openmetadata_client.OpenMetadataClient", FakeOMClient)
    result = get_table_info("svc.db.orders")
    assert result["om_reachable"] is True
    assert result["name"] == "orders"
    assert result["column_count"] == 2
    assert result["tags"] == ["PII.Sensitive"]
    assert result["owners"] == [{"name": "dre-oncall", "type": "user"}]
    assert result["columns"][0]["name"] == "order_id"


def test_mcp_tools_are_callable():
    assert callable(list_recent_failures)
    assert callable(get_table_info)
