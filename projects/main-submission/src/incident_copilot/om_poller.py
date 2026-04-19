"""OpenMetadata event poller — fallback when webhook-based alerting is unavailable.

Polls OpenMetadata's test case results endpoint, filters newly-failed cases,
and dispatches each through the copilot pipeline via a caller-provided fn.

The OM client is injected so tests can mock it. In production, the client comes
from `openmetadata_client.OpenMetadataClient.from_env()`.
"""
from typing import Any, Callable


def _extract_timestamp(event: dict) -> int | None:
    tcr = event.get("testCaseResult") or {}
    ts = tcr.get("timestamp")
    try:
        return int(ts)
    except (TypeError, ValueError):
        return None


def _is_failed(event: dict) -> bool:
    status = ((event.get("testCaseResult") or {}).get("testCaseStatus") or "").lower()
    return status == "failed"


def _event_to_webhook_payload(event: dict) -> dict:
    """Shape a /v1/testCase/testCaseResults row like an alert webhook payload."""
    test_case = event.get("testCase") or {}
    return {
        "entity": {
            "id": test_case.get("id", ""),
            "fullyQualifiedName": test_case.get("fullyQualifiedName", ""),
            "testCaseResult": event.get("testCaseResult", {}),
        },
        "timestamp": (event.get("testCaseResult") or {}).get("timestamp"),
    }


def poll_once(
    om_client: Any,
    dispatch_fn: Callable[[dict], Any],
    cursor: int,
    limit: int = 50,
) -> dict:
    """Poll OM once. Returns summary including updated cursor.

    `cursor` is a millisecond epoch; only events newer than cursor are processed.
    `dispatch_fn` receives a webhook-shaped payload and runs the pipeline.
    """
    summary = {
        "fetched": 0,
        "dispatched": 0,
        "dispatch_errors": 0,
        "new_cursor": cursor,
    }

    try:
        events = om_client.fetch_recent_test_case_results(since_ms=cursor, limit=limit) or []
    except Exception as exc:
        summary["error"] = str(exc)
        return summary

    summary["fetched"] = len(events)
    if not events:
        return summary

    latest_ts = cursor
    for event in events:
        ts = _extract_timestamp(event)
        if ts is not None and ts > latest_ts:
            latest_ts = ts

        if not _is_failed(event):
            continue

        payload = _event_to_webhook_payload(event)
        try:
            dispatch_fn(payload)
            summary["dispatched"] += 1
        except Exception:
            summary["dispatch_errors"] += 1

    summary["new_cursor"] = latest_ts
    return summary
