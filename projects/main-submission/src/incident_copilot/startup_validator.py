"""Startup-time config sanity checks. Warns on missing optional integrations, errors
on misconfigured required fields. Never raises — caller decides how to react."""
from dataclasses import dataclass, field

from incident_copilot.config import AppConfig


@dataclass(frozen=True)
class ValidationReport:
    ok: bool
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def validate_startup(cfg: AppConfig) -> ValidationReport:
    warnings: list[str] = []
    errors: list[str] = []

    if cfg.port <= 0 or cfg.port > 65535:
        errors.append(f"invalid port {cfg.port} (must be 1..65535)")

    # OpenMetadata: either both url+token, or neither
    has_url = bool(cfg.openmetadata_base_url)
    has_token = bool(cfg.openmetadata_jwt_token)
    if has_url and not has_token:
        errors.append("OPENMETADATA_BASE_URL set but OPENMETADATA_JWT_TOKEN is missing")
    elif has_token and not has_url:
        errors.append("OPENMETADATA_JWT_TOKEN set but OPENMETADATA_BASE_URL is missing")
    elif not has_url and not has_token:
        warnings.append("OpenMetadata not configured — service will use fixture data for context resolution")

    if cfg.use_om_mcp and not cfg.openmetadata_mcp_url:
        warnings.append("USE_OM_MCP=true but OPENMETADATA_MCP_URL is unset — MCP resolution will fall back to HTTP")

    if not cfg.has_slack:
        warnings.append("Slack webhook not configured — delivery will fall back to local mirror only")

    if not cfg.has_ai:
        warnings.append("OpenRouter API key not set — RCA and recommendation narratives will use deterministic templates")

    return ValidationReport(ok=not errors, warnings=warnings, errors=errors)
