#!/usr/bin/env python3
"""One-shot OpenMetadata validation: seed-check + replay + assert no OM fallback."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib import error, parse, request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from incident_copilot.live_validation import candidate_entity_fqns, require_live_openmetadata_resolution
from incident_copilot.live_validation import bootstrap_target_fqn, parse_table_fqn
from incident_copilot.orchestrator import run_pipeline


def _normalize_base_url(value: str | None) -> str:
    raw = (value or "http://localhost:8585/api").rstrip("/")
    parts = parse.urlparse(raw)
    path = parts.path or ""
    if path.endswith("/api/v1"):
        path = path[:-3]
    elif path in ("", "/"):
        path = "/api"
    elif not path.endswith("/api"):
        path = f"{path}/api"
    return parse.urlunparse((parts.scheme or "http", parts.netloc, path.rstrip("/"), "", "", ""))


def _http_json(url: str, *, method: str, payload: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url, method=method, headers=headers, data=body)
    try:
        with request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {})
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail) if detail else {}
        except json.JSONDecodeError:
            parsed = {"message": detail}
        return exc.code, parsed


def _login(base_url: str, email: str, password_b64: str) -> str:
    code, payload = _http_json(
        f"{base_url}/v1/users/login",
        method="POST",
        payload={"email": email, "password": password_b64},
    )
    token = payload.get("accessToken")
    if code != 200 or not token:
        raise RuntimeError(f"OpenMetadata login failed ({code}): {payload}")
    return token


def _table_exists(base_url: str, token: str, fqn: str) -> bool:
    quoted = parse.quote(fqn, safe="")
    code, _payload = _http_json(
        f"{base_url}/v1/tables/name/{quoted}?fields=owners,tags,databaseSchema",
        method="GET",
        token=token,
    )
    return code == 200


def _get_database_service(base_url: str, token: str, service_name: str) -> dict | None:
    quoted = parse.quote(service_name, safe="")
    code, payload = _http_json(
        f"{base_url}/v1/services/databaseServices/name/{quoted}",
        method="GET",
        token=token,
    )
    return payload if code == 200 else None


def _get_database(base_url: str, token: str, database_fqn: str) -> dict | None:
    quoted = parse.quote(database_fqn, safe="")
    code, payload = _http_json(
        f"{base_url}/v1/databases/name/{quoted}",
        method="GET",
        token=token,
    )
    return payload if code == 200 else None


def _get_database_schema(base_url: str, token: str, schema_fqn: str) -> dict | None:
    quoted = parse.quote(schema_fqn, safe="")
    code, payload = _http_json(
        f"{base_url}/v1/databaseSchemas/name/{quoted}",
        method="GET",
        token=token,
    )
    return payload if code == 200 else None


def _create_database_service(base_url: str, token: str, service_name: str, service_type: str) -> dict:
    # Minimal dev-safe connection payload for local validation instances.
    payload = {
        "name": service_name,
        "serviceType": service_type,
        "connection": {
            "config": {
                "type": service_type,
                "hostPort": "localhost:3306",
                "username": "openmetadata",
                "password": "openmetadata",
            }
        },
    }
    code, out = _http_json(
        f"{base_url}/v1/services/databaseServices",
        method="POST",
        payload=payload,
        token=token,
    )
    if code not in (200, 201):
        raise RuntimeError(f"Create database service failed ({code}): {out}")
    return out


def _create_database(base_url: str, token: str, database_name: str, service_fqn: str) -> dict:
    payload = {
        "name": database_name,
        "service": service_fqn,
    }
    code, out = _http_json(
        f"{base_url}/v1/databases",
        method="POST",
        payload=payload,
        token=token,
    )
    if code not in (200, 201):
        raise RuntimeError(f"Create database failed ({code}): {out}")
    return out


def _create_database_schema(base_url: str, token: str, schema_name: str, database_fqn: str) -> dict:
    payload = {
        "name": schema_name,
        "database": database_fqn,
    }
    code, out = _http_json(
        f"{base_url}/v1/databaseSchemas",
        method="POST",
        payload=payload,
        token=token,
    )
    if code not in (200, 201):
        raise RuntimeError(f"Create database schema failed ({code}): {out}")
    return out


def _create_table(base_url: str, token: str, table_name: str, schema_fqn: str) -> dict:
    payload = {
        "name": table_name,
        "tableType": "Regular",
        "databaseSchema": schema_fqn,
        "columns": [
            {
                "name": "customer_id",
                "dataType": "INT",
                "dataLength": 10,
            },
            {
                "name": "email",
                "dataType": "VARCHAR",
                "dataLength": 255,
            },
            {
                "name": "updated_at",
                "dataType": "TIMESTAMP",
            },
        ],
    }
    code, out = _http_json(
        f"{base_url}/v1/tables",
        method="POST",
        payload=payload,
        token=token,
    )
    if code not in (200, 201):
        raise RuntimeError(f"Create table failed ({code}): {out}")
    return out


def _ensure_seeded_hierarchy(
    base_url: str,
    token: str,
    entity_fqn: str,
    service_hints: list[str],
    service_type: str,
) -> tuple[str, list[str]]:
    actions: list[str] = []
    candidates = candidate_entity_fqns(entity_fqn, service_hints)
    for fqn in candidates:
        if _table_exists(base_url, token, fqn):
            return fqn, actions

    target_fqn = bootstrap_target_fqn(entity_fqn, service_hints)
    service_name, database_name, schema_name, table_name = parse_table_fqn(target_fqn)
    database_fqn = f"{service_name}.{database_name}"
    schema_fqn = f"{database_fqn}.{schema_name}"

    service = _get_database_service(base_url, token, service_name)
    if service is None:
        _create_database_service(base_url, token, service_name, service_type)
        actions.append(f"created_service:{service_name}")
        service = _get_database_service(base_url, token, service_name)
    if service is None:
        raise RuntimeError(f"Service bootstrap failed for {service_name}")

    database = _get_database(base_url, token, database_fqn)
    if database is None:
        _create_database(base_url, token, database_name, service_name)
        actions.append(f"created_database:{database_fqn}")
        database = _get_database(base_url, token, database_fqn)
    if database is None:
        raise RuntimeError(f"Database bootstrap failed for {database_fqn}")

    schema = _get_database_schema(base_url, token, schema_fqn)
    if schema is None:
        _create_database_schema(base_url, token, schema_name, database_fqn)
        actions.append(f"created_schema:{schema_fqn}")
        schema = _get_database_schema(base_url, token, schema_fqn)
    if schema is None:
        raise RuntimeError(f"Schema bootstrap failed for {schema_fqn}")

    if not _table_exists(base_url, token, target_fqn):
        _create_table(base_url, token, table_name, schema_fqn)
        actions.append(f"created_table:{target_fqn}")
    if not _table_exists(base_url, token, target_fqn):
        raise RuntimeError(f"Table bootstrap failed for {target_fqn}")

    return target_fqn, actions


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", default="runtime/fixtures/replay_event.json")
    parser.add_argument("--output", default="runtime/local_mirror/live_om_validation_report.json")
    parser.add_argument("--openmetadata-base-url", default=os.environ.get("OPENMETADATA_BASE_URL", "http://localhost:8585/api"))
    parser.add_argument("--admin-email", default=os.environ.get("OM_ADMIN_EMAIL", "admin@open-metadata.org"))
    parser.add_argument("--admin-password-b64", default=os.environ.get("OM_ADMIN_PASSWORD_B64", "YWRtaW4="))
    parser.add_argument(
        "--service-hints",
        default=os.environ.get("OPENMETADATA_FQN_SERVICE_HINTS", "demo_mysql"),
        help="Comma-separated service prefixes used to map 3-part fixture FQNs.",
    )
    parser.add_argument(
        "--service-type",
        default=os.environ.get("OPENMETADATA_SERVICE_TYPE", "Mysql"),
        help="OpenMetadata database service type used for create-if-missing bootstrap.",
    )
    parser.add_argument(
        "--seed-create-if-missing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Create missing service/database/schema/table entities before replay assertion.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    base_url = _normalize_base_url(args.openmetadata_base_url)
    replay_event = json.loads(Path(args.replay).read_text(encoding="utf-8"))
    hints = [h.strip() for h in args.service_hints.split(",") if h.strip()]
    token = _login(base_url, args.admin_email, args.admin_password_b64)

    candidate_fqns = candidate_entity_fqns(replay_event.get("entity_fqn", ""), hints)
    created_actions: list[str] = []
    seeded_fqn = next((fqn for fqn in candidate_fqns if _table_exists(base_url, token, fqn)), None)
    if not seeded_fqn:
        if not args.seed_create_if_missing:
            raise RuntimeError(
                "Seed check failed: no replay table candidate exists in OpenMetadata. "
                f"checked={candidate_fqns}"
            )
        seeded_fqn, created_actions = _ensure_seeded_hierarchy(
            base_url,
            token,
            replay_event.get("entity_fqn", ""),
            hints,
            args.service_type,
        )

    os.environ["OPENMETADATA_BASE_URL"] = base_url
    os.environ["OPENMETADATA_JWT_TOKEN"] = token
    os.environ["OM_CONTEXT_SOURCE"] = "direct_http"
    os.environ["OPENMETADATA_FQN_SERVICE_HINTS"] = ",".join(hints)

    result = run_pipeline(replay_event, None, slack_sender=lambda _brief: False)
    require_live_openmetadata_resolution(result["fallback_reason_codes"])

    report = {
        "status": "ok",
        "incident_id": result["brief"]["incident_id"],
        "seeded_entity_fqn": seeded_fqn,
        "created_actions": created_actions,
        "checked_candidates": candidate_fqns,
        "who_acts_first": result["brief"]["who_acts_first"]["text"],
        "fallback_reason_codes": result["fallback_reason_codes"],
        "policy_state": result["brief"]["policy_state"],
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Validation: {report['status']}")
    print(f"Incident: {report['incident_id']}")
    print(f"Seeded entity: {report['seeded_entity_fqn']}")
    print(f"Who acts first: {report['who_acts_first']}")
    print(f"Fallback codes: {report['fallback_reason_codes']}")
    print(f"Report: {out}")


if __name__ == "__main__":
    main()
