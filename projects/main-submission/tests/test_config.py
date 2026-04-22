import os
from unittest.mock import patch

from incident_copilot.config import load_config


def test_defaults_when_nothing_set():
    with patch.dict(os.environ, {}, clear=True):
        cfg = load_config()
        assert cfg.db_path.endswith("incidents.db")
        assert cfg.default_channel == "#metadata-incidents"
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 8080
        assert cfg.has_openmetadata is False


def test_reads_security_env():
    with patch.dict(
        os.environ,
        {
            "COPILOT_WEBHOOK_SECRET": "om-secret",
            "COPILOT_API_KEY": "api-key",
            "COPILOT_APPROVER_USERS": "U1,steward",
        },
        clear=True,
    ):
        cfg = load_config()
        assert cfg.webhook_signing_secret == "om-secret"
        assert cfg.api_key == "api-key"
        assert cfg.approver_users == "U1,steward"


def test_reads_openmetadata_from_env():
    env = {
        "OPENMETADATA_BASE_URL": "http://om:8585/api",
        "OPENMETADATA_JWT_TOKEN": "jwt-token",
    }
    with patch.dict(os.environ, env, clear=True):
        cfg = load_config()
        assert cfg.openmetadata_base_url == "http://om:8585/api"
        assert cfg.openmetadata_jwt_token == "jwt-token"
        assert cfg.has_openmetadata is True


def test_reads_slack_webhook():
    with patch.dict(os.environ, {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/x"}, clear=True):
        cfg = load_config()
        assert cfg.slack_webhook_url == "https://hooks.slack.com/x"
        assert cfg.has_slack is True


def test_port_respects_env():
    with patch.dict(os.environ, {"COPILOT_PORT": "9090"}, clear=True):
        cfg = load_config()
        assert cfg.port == 9090


def test_db_path_respects_env(tmp_path):
    with patch.dict(os.environ, {"COPILOT_DB_PATH": str(tmp_path / "x.db")}, clear=True):
        cfg = load_config()
        assert cfg.db_path == str(tmp_path / "x.db")
