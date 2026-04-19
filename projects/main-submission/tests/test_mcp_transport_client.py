import json
from io import BytesIO
from urllib import error
from unittest.mock import patch

import pytest

from incident_copilot.mcp_transport_client import MCPTransportClient, MCPTransportClientError, MCPTransportSettings


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_fetch_incident_context_posts_jsonrpc_request_and_returns_result():
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["method"] = req.method
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse(
            {
                "jsonrpc": "2.0",
                "id": "1",
                "result": {
                    "failed_test": {"name": "tc-null-ratio", "message": "null ratio exceeded"},
                    "lineage": [],
                    "owners": {},
                    "classifications": {},
                },
            }
        )

    client = MCPTransportClient(
        MCPTransportSettings(
            url="http://mcp.example/api",
            tool="resolve_incident_context",
            method="tools/call",
            timeout_seconds=7.5,
            token="secret-token",
        )
    )

    with patch("incident_copilot.mcp_transport_client.request.urlopen", side_effect=fake_urlopen):
        result = client.fetch_incident_context({"entity_fqn": "svc.db.orders", "test_case_id": "tc-null-ratio"}, max_depth=4)

    assert captured["url"] == "http://mcp.example/api"
    assert captured["method"] == "POST"
    assert captured["timeout"] == 7.5
    assert captured["headers"]["Authorization"] == "Bearer secret-token"
    assert captured["body"] == {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "tools/call",
        "params": {
            "name": "resolve_incident_context",
            "arguments": {
                "envelope": {"entity_fqn": "svc.db.orders", "test_case_id": "tc-null-ratio"},
                "max_depth": 4,
            },
        },
    }
    assert result["failed_test"]["name"] == "tc-null-ratio"


def test_fetch_incident_context_prefers_structured_content_payload():
    client = MCPTransportClient(
        MCPTransportSettings(
            url="http://mcp.example/api",
            tool="resolve_incident_context",
            method="tools/call",
            timeout_seconds=1,
            token=None,
        )
    )

    with patch(
        "incident_copilot.mcp_transport_client.request.urlopen",
        return_value=FakeResponse(
            {
                "jsonrpc": "2.0",
                "id": "1",
                "result": {
                    "structuredContent": {
                        "failed_test": {"name": "tc-null-ratio", "message": "structured payload"},
                        "lineage": [],
                        "owners": {},
                        "classifications": {},
                    },
                    "content": [{"type": "text", "text": "ignored"}],
                },
            }
        ),
    ):
        result = client.fetch_incident_context({"entity_fqn": "svc.db.orders", "test_case_id": "tc-null-ratio"})

    assert result["failed_test"]["message"] == "structured payload"


def test_fetch_incident_context_raises_on_http_error():
    client = MCPTransportClient(
        MCPTransportSettings(
            url="http://mcp.example/api",
            tool="resolve_incident_context",
            method="tools/call",
            timeout_seconds=1,
            token=None,
        )
    )

    http_error = error.HTTPError(
        url="http://mcp.example/api",
        code=502,
        msg="Bad Gateway",
        hdrs=None,
        fp=BytesIO(b"upstream unavailable"),
    )

    with patch("incident_copilot.mcp_transport_client.request.urlopen", side_effect=http_error):
        with pytest.raises(MCPTransportClientError, match="MCP HTTP 502"):
            client.fetch_incident_context({"entity_fqn": "svc.db.orders"}, max_depth=2)


def test_fetch_incident_context_raises_on_url_error():
    client = MCPTransportClient(
        MCPTransportSettings(
            url="http://mcp.example/api",
            tool="resolve_incident_context",
            method="tools/call",
            timeout_seconds=1,
            token=None,
        )
    )

    with patch(
        "incident_copilot.mcp_transport_client.request.urlopen",
        side_effect=error.URLError("temporary failure"),
    ):
        with pytest.raises(MCPTransportClientError, match="MCP connection error"):
            client.fetch_incident_context({"entity_fqn": "svc.db.orders"}, max_depth=2)


def test_fetch_incident_context_raises_on_rpc_error():
    client = MCPTransportClient(
        MCPTransportSettings(
            url="http://mcp.example/api",
            tool="resolve_incident_context",
            method="tools/call",
            timeout_seconds=1,
            token=None,
        )
    )

    with patch(
        "incident_copilot.mcp_transport_client.request.urlopen",
        return_value=FakeResponse({"jsonrpc": "2.0", "id": "1", "error": {"code": -32603, "message": "boom"}}),
    ):
        with pytest.raises(MCPTransportClientError, match="boom"):
            client.fetch_incident_context({"entity_fqn": "svc.db.orders"}, max_depth=2)
