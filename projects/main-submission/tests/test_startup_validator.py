from incident_copilot.config import AppConfig
from incident_copilot.startup_validator import validate_startup


def _cfg(**overrides) -> AppConfig:
    defaults = dict(
        host="0.0.0.0", port=8080, db_path="runtime/x.db",
        default_channel="#x",
        openmetadata_base_url=None, openmetadata_jwt_token=None,
        openmetadata_mcp_url=None, slack_webhook_url=None,
        openrouter_api_key=None, use_om_mcp=False,
    )
    defaults.update(overrides)
    return AppConfig(**defaults)


def test_all_missing_yields_warnings_not_errors():
    report = validate_startup(_cfg())
    assert report.ok is True
    assert any("OpenMetadata" in w for w in report.warnings)
    assert any("Slack" in w for w in report.warnings)
    assert any("OpenRouter" in w for w in report.warnings)
    assert report.errors == []


def test_everything_configured_is_clean():
    report = validate_startup(_cfg(
        openmetadata_base_url="http://om:8585/api",
        openmetadata_jwt_token="jwt",
        slack_webhook_url="https://hooks.slack.com/x",
        openrouter_api_key="sk-or-x",
    ))
    assert report.ok is True
    assert report.warnings == []
    assert report.errors == []


def test_partial_openmetadata_config_is_error():
    report = validate_startup(_cfg(openmetadata_base_url="http://om:8585/api"))
    assert report.ok is False
    assert any("OPENMETADATA_JWT_TOKEN" in e for e in report.errors)


def test_invalid_port_is_error():
    report = validate_startup(_cfg(port=0))
    assert report.ok is False
    assert any("port" in e.lower() for e in report.errors)


def test_use_om_mcp_without_url_is_warning():
    report = validate_startup(_cfg(use_om_mcp=True))
    assert report.ok is True
    assert any("OPENMETADATA_MCP_URL" in w for w in report.warnings)
