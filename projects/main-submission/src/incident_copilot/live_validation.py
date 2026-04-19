from __future__ import annotations

from typing import Iterable

_OM_DEGRADATION_CODES = {
    "OM_HTTP_FALLBACK_TO_FIXTURE",
    "OM_MCP_FALLBACK_TO_HTTP",
    "MISSING_OWNER_METADATA",
}


def candidate_entity_fqns(entity_fqn: str, service_hints: Iterable[str]) -> list[str]:
    candidates = [entity_fqn]
    if entity_fqn and entity_fqn.count(".") == 2:
        for hint in service_hints:
            part = (hint or "").strip()
            if not part:
                continue
            mapped = f"{part}.{entity_fqn}"
            if mapped not in candidates:
                candidates.append(mapped)
    return candidates


def is_openmetadata_context_degraded(fallback_reason_codes: Iterable[str]) -> bool:
    return any(code in _OM_DEGRADATION_CODES for code in fallback_reason_codes)


def require_live_openmetadata_resolution(fallback_reason_codes: Iterable[str]) -> None:
    codes = list(fallback_reason_codes)
    if is_openmetadata_context_degraded(codes):
        raise RuntimeError(
            "OpenMetadata live-context degradation detected: "
            + ", ".join(code for code in codes if code in _OM_DEGRADATION_CODES)
        )


def parse_table_fqn(entity_fqn: str) -> tuple[str, str, str, str]:
    parts = (entity_fqn or "").split(".")
    if len(parts) != 4 or not all(parts):
        raise ValueError(f"Expected service.database.schema.table FQN, got: {entity_fqn!r}")
    return parts[0], parts[1], parts[2], parts[3]


def bootstrap_target_fqn(entity_fqn: str, service_hints: Iterable[str]) -> str:
    candidates = candidate_entity_fqns(entity_fqn, service_hints)
    # For fixture 3-part FQNs, prefer first service-prefixed candidate for bootstrap.
    if entity_fqn and entity_fqn.count(".") == 2 and len(candidates) > 1:
        return candidates[1]
    return entity_fqn
