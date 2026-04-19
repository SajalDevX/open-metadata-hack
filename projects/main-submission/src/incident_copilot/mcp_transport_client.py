import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, request


class MCPTransportClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class MCPTransportSettings:
    url: str
    tool: str
    method: str
    timeout_seconds: float
    token: str | None = None


class MCPTransportClient:
    def __init__(self, settings: MCPTransportSettings):
        self.settings = settings

    @classmethod
    def from_env(cls) -> "MCPTransportClient":
        return cls(
            MCPTransportSettings(
                url=(os.environ.get("OPENMETADATA_MCP_URL") or "http://localhost:8787/mcp").strip(),
                tool=(os.environ.get("OPENMETADATA_MCP_TOOL") or "resolve_incident_context").strip(),
                method=(os.environ.get("OPENMETADATA_MCP_METHOD") or "tools/call").strip(),
                timeout_seconds=float(os.environ.get("OPENMETADATA_MCP_TIMEOUT_SECONDS", "3")),
                token=os.environ.get("OPENMETADATA_MCP_TOKEN") or None,
            )
        )

    def _build_request(self, envelope: dict[str, Any], max_depth: int) -> request.Request:
        body = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": self.settings.method,
            "params": {
                "name": self.settings.tool,
                "arguments": {
                    "envelope": envelope,
                    "max_depth": max_depth,
                },
            },
        }
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.settings.token:
            headers["Authorization"] = f"Bearer {self.settings.token}"

        return request.Request(
            self.settings.url,
            data=json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8"),
            headers=headers,
            method="POST",
        )

    def _unwrap_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("error"):
            error_payload = payload["error"]
            message = error_payload.get("message") if isinstance(error_payload, dict) else str(error_payload)
            raise MCPTransportClientError(message or "MCP request failed")

        result = payload.get("result")
        if isinstance(result, dict):
            structured_content = result.get("structuredContent")
            if isinstance(structured_content, dict):
                return structured_content
            if "content" in result and isinstance(result["content"], list):
                for item in result["content"]:
                    if isinstance(item, dict) and isinstance(item.get("json"), dict):
                        return item["json"]
            return result

        if isinstance(payload.get("content"), list):
            for item in payload["content"]:
                if isinstance(item, dict) and isinstance(item.get("json"), dict):
                    return item["json"]

        raise MCPTransportClientError("MCP response did not contain a JSON object result")

    def fetch_incident_context(self, envelope: dict[str, Any], max_depth: int = 2) -> dict[str, Any]:
        req = self._build_request(envelope, max_depth)
        try:
            with request.urlopen(req, timeout=self.settings.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise MCPTransportClientError(f"MCP HTTP {exc.code} for {self.settings.url}: {detail}") from exc
        except error.URLError as exc:
            raise MCPTransportClientError(f"MCP connection error for {self.settings.url}: {exc.reason}") from exc

        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise MCPTransportClientError(f"Invalid JSON returned by MCP endpoint: {exc}") from exc

        if not isinstance(payload, dict):
            raise MCPTransportClientError("MCP response must be a JSON object")

        return self._unwrap_result(payload)
