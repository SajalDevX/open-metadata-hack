import json
import os
from urllib.request import Request, urlopen


_ENV_WEBHOOK_KEYS = (
    "SLACK_WEBHOOK_URL",
    "SLACK_WEBHOOK",
)


def get_slack_webhook_url(env: dict | None = None) -> str | None:
    source = os.environ if env is None else env
    for key in _ENV_WEBHOOK_KEYS:
        value = source.get(key)
        if value:
            return value
    return None


def _render_slack_message(payload: dict) -> dict | None:
    if not isinstance(payload, dict):
        return None

    brief = payload.get("brief")
    if brief is None:
        brief = {}
    if not isinstance(brief, dict):
        return None

    incident_id = payload.get("incident_id") or brief.get("incident_id") or "unknown"
    policy = brief.get("policy_state", "allowed")

    lines = [f"Incident {incident_id}"]
    section_blocks = []
    if isinstance(brief, dict):
        for label, key in (
            ("Failed", "what_failed"),
            ("Impact", "what_is_impacted"),
            ("Responder", "who_acts_first"),
            ("Next", "what_to_do_next"),
        ):
            block = brief.get(key)
            if isinstance(block, dict):
                text = block.get("text")
                if text:
                    lines.append(f"{label}: {text}")
                    section_blocks.append({
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*{label}:*\n{text}"},
                    })

    # Header with incident id + policy badge
    policy_emoji = ":rotating_light:" if policy == "approval_required" else ":white_check_mark:"
    header_block = {
        "type": "header",
        "text": {"type": "plain_text", "text": f"{policy_emoji} Incident {incident_id} · {policy}"},
    }

    # Interactive action buttons — action_id values must match slack_actions.py
    buttons = [
        {"type": "button", "text": {"type": "plain_text", "text": "Acknowledge"},
         "action_id": "ack", "value": incident_id},
    ]
    if policy == "approval_required":
        buttons.extend([
            {"type": "button", "text": {"type": "plain_text", "text": "Approve"},
             "style": "primary", "action_id": "approve", "value": incident_id},
            {"type": "button", "text": {"type": "plain_text", "text": "Deny"},
             "style": "danger", "action_id": "deny", "value": incident_id},
        ])
    actions_block = {"type": "actions", "elements": buttons}

    return {
        "text": "\n".join(lines),   # fallback for notifications / old clients
        "unfurl_links": False,
        "blocks": [header_block, *section_blocks, actions_block],
    }


def send_slack_payload(
    payload: dict,
    webhook_url: str | None = None,
    timeout_seconds: float = 5.0,
    opener=None,
) -> bool:
    url = webhook_url or get_slack_webhook_url()
    if not url:
        return False

    message = _render_slack_message(payload)
    if not isinstance(message, dict):
        return False

    request_body = json.dumps(message, sort_keys=True, separators=(",", ":"), default=str)
    request = Request(
        url,
        data=request_body.encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    opener_fn = opener or urlopen
    try:
        with opener_fn(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", None)
            if status is None and hasattr(response, "getcode"):
                status = response.getcode()
            return status is None or 200 <= int(status) < 300
    except Exception:
        return False


def build_slack_sender(env: dict | None = None, timeout_seconds: float = 5.0, opener=None):
    webhook_url = get_slack_webhook_url(env)
    if not webhook_url:
        return None

    def sender(payload: dict) -> bool:
        return send_slack_payload(
            payload,
            webhook_url=webhook_url,
            timeout_seconds=timeout_seconds,
            opener=opener,
        )

    return sender
