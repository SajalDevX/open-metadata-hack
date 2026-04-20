"""Tests for POST /slack/commands endpoint."""
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from incident_copilot.app import create_app
from incident_copilot.config import AppConfig


def _make_config(**overrides) -> AppConfig:
    defaults = dict(
        host="127.0.0.1",
        port=8080,
        db_path=":memory:",
        default_channel="#test",
        openmetadata_base_url=None,
        openmetadata_jwt_token=None,
        openmetadata_mcp_url=None,
        slack_webhook_url=None,
        openrouter_api_key=None,
        use_om_mcp=False,
        enable_poller=False,
        poller_interval_seconds=60.0,
    )
    defaults.update(overrides)
    return AppConfig(**defaults)


def _cmd_body(**fields) -> bytes:
    return urlencode(fields).encode()


def test_slack_commands_empty_text_returns_usage():
    app = create_app(_make_config(), retry_interval_seconds=0)
    client = TestClient(app)
    resp = client.post(
        "/slack/commands",
        content=_cmd_body(command="/metadata", text=""),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["response_type"] == "ephemeral"
    assert "Usage" in body["text"]


def test_slack_commands_no_om_returns_not_configured():
    app = create_app(_make_config(), retry_interval_seconds=0)
    client = TestClient(app)
    resp = client.post(
        "/slack/commands",
        content=_cmd_body(command="/metadata", text="search orders"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["response_type"] == "ephemeral"
    assert "not configured" in body["text"].lower() or "OpenMetadata" in body["text"]


def test_slack_commands_strips_search_prefix():
    """The command text 'search orders' strips to 'orders' before querying."""
    cfg = _make_config(
        openmetadata_base_url="http://om-test:8585/api",
        openmetadata_jwt_token="test-token",
    )
    app = create_app(cfg, retry_interval_seconds=0)
    client = TestClient(app)

    searched_queries = []

    class FakeOMClient:
        @classmethod
        def from_env(cls):
            return cls()

        def search_entities(self, query, limit=5):
            searched_queries.append(query)
            return []

    import incident_copilot.app as app_module
    import importlib
    orig = None
    try:
        import incident_copilot.openmetadata_client as om_mod
        orig = om_mod.OpenMetadataClient
        om_mod.OpenMetadataClient = FakeOMClient

        resp = client.post(
            "/slack/commands",
            content=_cmd_body(command="/metadata", text="search orders"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert searched_queries == ["orders"]
    finally:
        if orig:
            om_mod.OpenMetadataClient = orig


def test_slack_commands_returns_blocks_on_results():
    cfg = _make_config(
        openmetadata_base_url="http://om-test:8585/api",
        openmetadata_jwt_token="test-token",
    )
    app = create_app(cfg, retry_interval_seconds=0)
    client = TestClient(app)

    fake_results = [
        {
            "fullyQualifiedName": "svc.db.orders",
            "description": "Daily orders table",
            "owners": [{"name": "dre-oncall"}],
        },
        {
            "fullyQualifiedName": "svc.db.order_items",
            "description": "Order line items",
            "owners": [],
        },
    ]

    class FakeOMClient:
        @classmethod
        def from_env(cls):
            return cls()

        def search_entities(self, query, limit=5):
            return fake_results

    import incident_copilot.openmetadata_client as om_mod
    orig = om_mod.OpenMetadataClient
    try:
        om_mod.OpenMetadataClient = FakeOMClient
        resp = client.post(
            "/slack/commands",
            content=_cmd_body(command="/metadata", text="orders"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["response_type"] == "ephemeral"
        assert "blocks" in body
        block_texts = " ".join(
            b.get("text", {}).get("text", "") for b in body["blocks"]
        )
        assert "svc.db.orders" in block_texts
        assert "dre-oncall" in block_texts
    finally:
        om_mod.OpenMetadataClient = orig


def test_slack_commands_no_results_returns_not_found():
    cfg = _make_config(
        openmetadata_base_url="http://om-test:8585/api",
        openmetadata_jwt_token="test-token",
    )
    app = create_app(cfg, retry_interval_seconds=0)
    client = TestClient(app)

    class FakeOMClient:
        @classmethod
        def from_env(cls):
            return cls()

        def search_entities(self, query, limit=5):
            return []

    import incident_copilot.openmetadata_client as om_mod
    orig = om_mod.OpenMetadataClient
    try:
        om_mod.OpenMetadataClient = FakeOMClient
        resp = client.post(
            "/slack/commands",
            content=_cmd_body(command="/metadata", text="nonexistent_xyz"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "No results" in body.get("text", "")
    finally:
        om_mod.OpenMetadataClient = orig
