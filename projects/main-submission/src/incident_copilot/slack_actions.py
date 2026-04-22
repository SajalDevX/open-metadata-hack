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
from urllib import error, request
from urllib.parse import parse_qs


_ALLOWED_ACTIONS = ("ack", "approve", "deny")
_REPLAY_WINDOW_SECONDS = 300


class SlackActionError(Exception):
    pass


class SlackAuthorizationError(SlackActionError):
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
    channel = payload.get("channel") or {}
    return {
        "action": action_id,
        "incident_id": action.get("value") or "",
        "user_id": user.get("id") or "",
        "user_name": user.get("name") or "",
        "channel_id": channel.get("id") or "",
        "response_url": payload.get("response_url") or "",
    }


def _authorized_approver(user_id: str) -> bool:
    raw = os.environ.get("COPILOT_APPROVER_USERS", "")
    allowed = {item.strip().lower() for item in raw.split(",") if item.strip()}
    if not allowed:
        return False
    return user_id.lower() in allowed


def apply_action(store, incident_id: str, action: str, user_name: str, user_id: str = "") -> dict:
    row = store.fetch_by_id(incident_id)
    if row is None:
        raise SlackActionError(f"incident {incident_id} not found")
    brief = row.get("brief") or {}
    policy_state = brief.get("policy_state")
    required_role = brief.get("required_approver_role") or "data_steward"

    if action in {"approve", "deny"} and policy_state == "approval_required":
        if not _authorized_approver(user_id=user_id or ""):
            raise SlackAuthorizationError(
                f"user is not authorized to {action} (requires {required_role})"
            )

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


def post_ephemeral_via_bot(
    channel_id: str,
    user_id: str,
    text: str,
    bot_token: str | None = None,
    opener=None,
) -> bool:
    """Call chat.postEphemeral — shows a user-only message in the channel.

    Requires `SLACK_BOT_TOKEN` (xoxb-...). Returns True on success, False on any
    failure (including missing token). Safe to call unconditionally.
    """
    token = bot_token or os.environ.get("SLACK_BOT_TOKEN")
    if not (token and channel_id and user_id):
        return False

    body = json.dumps({
        "channel": channel_id,
        "user": user_id,
        "text": text,
    }).encode("utf-8")

    req = request.Request(
        "https://slack.com/api/chat.postEphemeral",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    opener_fn = opener or request.urlopen
    try:
        with opener_fn(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            return bool(data.get("ok"))
    except error.URLError:
        return False
    except Exception:
        return False


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
