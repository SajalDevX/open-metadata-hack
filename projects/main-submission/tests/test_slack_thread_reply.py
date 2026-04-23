import json
import pytest


def test_is_thread_reply_true():
    from incident_copilot.slack_thread_reply import is_thread_reply
    event = {"type": "message", "thread_ts": "123.456", "ts": "123.789", "text": "hello"}
    assert is_thread_reply(event) is True


def test_is_thread_reply_false_for_root_message():
    from incident_copilot.slack_thread_reply import is_thread_reply
    # root message: ts == thread_ts
    event = {"type": "message", "thread_ts": "123.456", "ts": "123.456", "text": "root"}
    assert is_thread_reply(event) is False


def test_is_thread_reply_false_for_bot_message():
    from incident_copilot.slack_thread_reply import is_thread_reply
    event = {"type": "message", "subtype": "bot_message", "thread_ts": "123.456", "ts": "999.1"}
    assert is_thread_reply(event) is False


def test_build_claude_prompt_contains_brief():
    from incident_copilot.slack_thread_reply import build_claude_prompt
    brief = {
        "incident_id": "inc-001",
        "policy_state": "approval_required",
        "what_failed": {"text": "null ratio exceeded 15%", "evidence_refs": []},
        "what_is_impacted": {"text": "users_curated (score:3.0)", "evidence_refs": []},
        "who_acts_first": {"text": "ingestion-bot", "evidence_refs": []},
        "what_to_do_next": {"text": "fix upstream", "evidence_refs": []},
    }
    prompt = build_claude_prompt(brief, user_question="Why did this fail?")
    assert "null ratio exceeded 15%" in prompt
    assert "Why did this fail?" in prompt
    assert "inc-001" in prompt


def test_handle_thread_event_replies_with_ai(tmp_path):
    from unittest.mock import patch, MagicMock
    from incident_copilot.store import IncidentStore
    from incident_copilot.slack_thread_reply import handle_thread_event

    store = IncidentStore(str(tmp_path / "incidents.db"))
    brief = {
        "incident_id": "inc-thread-001",
        "policy_state": "allowed",
        "what_failed": {"text": "volume drop", "evidence_refs": []},
        "what_is_impacted": {"text": "dashboard", "evidence_refs": []},
        "who_acts_first": {"text": "owner", "evidence_refs": []},
        "what_to_do_next": {"text": "check pipeline", "evidence_refs": []},
    }
    store.save_brief(brief, delivery_status="sent", primary_output="slack")
    store.save_thread_ts("inc-thread-001", "1111111111.000001")

    event = {
        "type": "message",
        "thread_ts": "1111111111.000001",
        "ts": "1111111112.000002",
        "text": "What caused this?",
        "channel": "C123",
        "user": "U456",
    }

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content="Volume dropped due to upstream pipeline failure."))]

    posted_messages = []

    def fake_post_message(channel, message, bot_token=None, thread_ts=None, **kw):
        posted_messages.append({"channel": channel, "thread_ts": thread_ts, "text": message.get("text")})
        return "1111111113.000003"

    with patch("incident_copilot.slack_thread_reply.get_client") as mock_client_fn, \
         patch("incident_copilot.slack_thread_reply.post_message", side_effect=fake_post_message):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_completion
        mock_client_fn.return_value = mock_client

        result = handle_thread_event(event, store=store, bot_token="xoxb-test")

    assert result is True
    assert len(posted_messages) == 1
    assert posted_messages[0]["thread_ts"] == "1111111111.000001"
    assert posted_messages[0]["channel"] == "C123"
    assert "pipeline failure" in posted_messages[0]["text"]


def test_handle_thread_event_ignores_unknown_thread(tmp_path):
    from incident_copilot.store import IncidentStore
    from incident_copilot.slack_thread_reply import handle_thread_event

    store = IncidentStore(str(tmp_path / "incidents.db"))
    event = {
        "type": "message",
        "thread_ts": "9999999999.000001",
        "ts": "9999999999.000002",
        "text": "random question",
        "channel": "C123",
        "user": "U456",
    }
    result = handle_thread_event(event, store=store, bot_token="xoxb-test")
    assert result is False
