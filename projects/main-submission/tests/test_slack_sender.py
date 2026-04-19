import json

from incident_copilot.slack_sender import build_slack_sender, send_slack_payload


def test_build_slack_sender_returns_none_without_webhook(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK", raising=False)

    assert build_slack_sender() is None


def test_build_slack_sender_uses_webhook_from_environment(monkeypatch):
    captured = []

    def fake_send_slack_payload(payload, webhook_url=None, timeout_seconds=5.0, opener=None):
        captured.append((payload, webhook_url, timeout_seconds, opener))
        return True

    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/services/T000/B000/TEST")
    monkeypatch.setattr("incident_copilot.slack_sender.send_slack_payload", fake_send_slack_payload)

    sender = build_slack_sender(timeout_seconds=1.5)

    assert sender is not None
    assert sender({"channel": "slack", "incident_id": "inc-1"}) is True
    assert captured == [
        ({"channel": "slack", "incident_id": "inc-1"}, "https://hooks.slack.test/services/T000/B000/TEST", 1.5, None)
    ]


def test_send_slack_payload_posts_json_to_webhook(monkeypatch):
    requests = []

    class FakeResponse:
        def __init__(self, status=200):
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"ok"

    def fake_urlopen(request, timeout=None):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/services/T000/B000/TEST")
    payload = {
        "channel": "slack",
        "brief": {
            "incident_id": "inc-7",
            "what_failed": {"text": "Database checksum mismatch", "evidence_refs": ["incident_ref"]},
            "what_is_impacted": {"text": "orders", "evidence_refs": ["lineage_ref"]},
        },
    }

    assert send_slack_payload(payload, opener=fake_urlopen) is True
    assert len(requests) == 1

    request, timeout = requests[0]
    assert timeout == 5.0
    assert request.full_url == "https://hooks.slack.test/services/T000/B000/TEST"
    assert request.get_header("Content-type") == "application/json"

    body = json.loads(request.data.decode("utf-8"))
    assert body["text"].startswith("Incident inc-7")
    assert "Database checksum mismatch" in body["text"]
    assert body["unfurl_links"] is False


def test_send_slack_payload_returns_false_on_transport_error(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise RuntimeError("network down")

    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/services/T000/B000/TEST")

    assert send_slack_payload({"channel": "slack", "brief": {"incident_id": "inc-8"}}, opener=fake_urlopen) is False
