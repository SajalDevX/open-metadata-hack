"""Centralized env-var configuration for the live incident copilot service."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    host: str
    port: int
    db_path: str
    default_channel: str
    openmetadata_base_url: str | None
    openmetadata_jwt_token: str | None
    openmetadata_mcp_url: str | None
    slack_webhook_url: str | None
    openrouter_api_key: str | None
    use_om_mcp: bool
    enable_poller: bool
    poller_interval_seconds: float

    @property
    def has_openmetadata(self) -> bool:
        return bool(self.openmetadata_base_url and self.openmetadata_jwt_token)

    @property
    def has_slack(self) -> bool:
        return bool(self.slack_webhook_url)

    @property
    def has_ai(self) -> bool:
        return bool(self.openrouter_api_key)


def _bool_env(key: str) -> bool:
    return (os.environ.get(key) or "").strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> AppConfig:
    return AppConfig(
        host=os.environ.get("COPILOT_HOST", "0.0.0.0"),
        port=int(os.environ.get("COPILOT_PORT", "8080")),
        db_path=os.environ.get("COPILOT_DB_PATH", "runtime/incidents.db"),
        default_channel=os.environ.get("COPILOT_DEFAULT_CHANNEL", "#metadata-incidents"),
        openmetadata_base_url=os.environ.get("OPENMETADATA_BASE_URL") or None,
        openmetadata_jwt_token=os.environ.get("OPENMETADATA_JWT_TOKEN") or None,
        openmetadata_mcp_url=os.environ.get("OPENMETADATA_MCP_URL") or None,
        slack_webhook_url=os.environ.get("SLACK_WEBHOOK_URL") or os.environ.get("SLACK_WEBHOOK") or None,
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY") or None,
        use_om_mcp=_bool_env("USE_OM_MCP"),
        enable_poller=_bool_env("COPILOT_ENABLE_POLLER"),
        poller_interval_seconds=float(os.environ.get("COPILOT_POLLER_INTERVAL_SECONDS", "60")),
    )
