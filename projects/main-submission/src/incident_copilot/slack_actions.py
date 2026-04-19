"""Slack interactivity — verify signed request, parse block_actions payload, update status.

Follows Slack's signing-secret scheme:
  base = "v0:" + X-Slack-Request-Timestamp + ":" + raw_body
  expected = "v0=" + HMAC-SHA256(signing_secret, base)
  reject if abs(now - ts) > 300s (replay protection)
"""
import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qs


_ALLOWED_ACTIONS = ("ack", "approve", "deny")
_REPLAY_WINDOW_SECONDS = 300


class SlackActionError(Exception):
    pass


def verify_slack_signature(raw_body: bytes, timestamp: str, signature: str, secret: str) -> bool:
    if not (raw_body is not None and timestamp and signature and secret):
        return False
    try:
        ts_int = int(timestamp)
    except (TypeError, ValueError):
        return False

    if abs(time.time() - ts_int) > _REPLAY_WINDOW_SECONDS:
        return False

    basestring = f"v0:{timestamp}:".encode() + raw_body
    expected = "v0=" + hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def parse_action_payload(raw_body: bytes) -> dict:
    """Slack POSTs form-encoded `payload=<json>`. Return the first action or raise."""
    form = parse_qs(raw_body.decode("utf-8", errors="replace"))
    payload_list = form.get("payload") or []
    if not payload_list:
        raise SlackActionError("no payload field")
    try:
        payload = json.loads(payload_list[0])
    except json.JSONDecodeError as exc:
        raise SlackActionError(f"invalid JSON payload: {exc}") from exc

    actions = payload.get("actions") or []
    if not actions:
        raise SlackActionError("no actions in payload")

    action = actions[0]
    action_id = action.get("action_id") or ""
    if action_id not in _ALLOWED_ACTIONS:
        raise SlackActionError(f"unknown action_id: {action_id!r}")

    user = payload.get("user") or {}
    return {
        "action": action_id,
        "incident_id": action.get("value") or "",
        "user_id": user.get("id") or "",
        "user_name": user.get("name") or "",
    }


def apply_action(store, incident_id: str, action: str, user_name: str) -> dict:
    row = store.fetch_by_id(incident_id)
    if row is None:
        raise SlackActionError(f"incident {incident_id} not found")

    new_status_map = {
        "ack": f"acked_by:{user_name or 'unknown'}",
        "approve": f"approved_by:{user_name or 'unknown'}",
        "deny": f"denied_by:{user_name or 'unknown'}",
    }
    status = new_status_map.get(action, row["delivery_status"])
    store.save_brief(
        brief=row["brief"],
        delivery_status=status,
        primary_output=row["primary_output"],
    )
    return {"incident_id": incident_id, "action": action, "status": status, "user": user_name}


_USER_VISIBLE = {
    "ack": ":white_check_mark: Acknowledged",
    "approve": ":white_check_mark: Approved",
    "deny": ":no_entry: Denied",
}


def render_slack_response(action: str, user_name: str, incident_id: str) -> dict:
    """Response body Slack renders inline after a button click.

    Replaces the original message so the brief visibly transforms into an
    "action taken" card. Works for both incoming-webhook-only and full bot apps.
    """
    label = _USER_VISIBLE.get(action, f"Action `{action}` recorded")
    user = f"@{user_name}" if user_name else "user"

    return {
        "replace_original": True,
        "text": f"{label} by {user} · incident {incident_id}",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{label.replace(':', '').strip()} · {incident_id}"},
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"{label} by *{user}*"},
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"Incident `{incident_id}` has been *{action}ed*. Full brief still available via the copilot dashboard."},
            },
        ],
    }
