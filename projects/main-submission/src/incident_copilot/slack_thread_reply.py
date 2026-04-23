"""Handle Slack thread replies — look up incident by thread_ts and reply with AI context."""
import json
import logging
import os

from incident_copilot.openrouter_client import get_client
from incident_copilot.slack_sender import post_message
from incident_copilot.store import IncidentStore

_SYSTEM_PROMPT = (
    "You are an incident response assistant for a data platform. "
    "You are given a data quality incident brief and an engineer's question about it. "
    "Answer concisely and accurately using only the information in the brief. "
    "If you cannot answer from the brief, say so — do not guess."
)

_FALLBACK_MODEL = "anthropic/claude-3-haiku"


def is_thread_reply(event: dict) -> bool:
    """Return True only for human replies in a thread (not root messages, not bot posts)."""
    if event.get("subtype"):
        return False
    thread_ts = event.get("thread_ts")
    ts = event.get("ts")
    if not thread_ts or not ts:
        return False
    return thread_ts != ts


def build_claude_prompt(brief: dict, user_question: str) -> str:
    brief_text = json.dumps(brief, indent=2, default=str)
    return (
        f"Incident ID: {brief.get('incident_id', 'unknown')}\n\n"
        f"Incident Brief:\n{brief_text}\n\n"
        f"Engineer's question: {user_question}"
    )


def handle_thread_event(
    event: dict,
    store: IncidentStore,
    bot_token: str | None = None,
    model: str | None = None,
) -> bool:
    """Process a Slack message event. Returns True if a reply was posted, False otherwise."""
    if not is_thread_reply(event):
        return False

    thread_ts = event["thread_ts"]
    incident_row = store.fetch_by_thread_ts(thread_ts)
    if not incident_row:
        return False

    brief = incident_row.get("brief") or {}
    user_question = event.get("text") or ""
    channel = event.get("channel") or ""

    if not user_question.strip() or not channel:
        return False

    reply_text = _generate_reply(brief, user_question, model=model)

    ts = post_message(
        channel=channel,
        message={"text": reply_text},
        bot_token=bot_token or os.environ.get("SLACK_BOT_TOKEN"),
        thread_ts=thread_ts,
    )
    return ts is not None


def _generate_reply(brief: dict, user_question: str, model: str | None = None) -> str:
    try:
        client = get_client()
        chosen_model = model or os.environ.get("OPENROUTER_MODEL", _FALLBACK_MODEL)
        prompt = build_claude_prompt(brief, user_question)
        response = client.chat.completions.create(
            model=chosen_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=400,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logging.warning("slack_thread_reply: AI call failed: %s", exc)
        return _fallback_reply(brief, user_question)


def _fallback_reply(brief: dict, user_question: str) -> str:
    what_failed = (brief.get("what_failed") or {}).get("text", "")
    who_acts = (brief.get("who_acts_first") or {}).get("text", "")
    policy = brief.get("policy_state", "allowed")
    return (
        f"*Incident {brief.get('incident_id', '')}* — AI response unavailable.\n"
        f"*What failed:* {what_failed}\n"
        f"*Responder:* {who_acts}\n"
        f"*Policy:* {policy}"
    )
