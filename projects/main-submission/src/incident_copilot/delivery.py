from incident_copilot.contracts import DeliveryResult


def deliver(brief, slack_sender, mirror_writer):
    slack_payload = {"channel": "slack", "brief": brief}
    local_mirror_payload = {"channel": "local_mirror", "brief": brief}
    mirror_writer(local_mirror_payload)
    slack_ok = bool(slack_sender(slack_payload))
    if slack_ok:
        result = DeliveryResult("sent", "rendered", "slack", [])
    else:
        result = DeliveryResult("failed", "rendered", "local_mirror", ["SLACK_SEND_FAILED"])
    return {
        "delivery": result,
        "slack_payload": slack_payload,
        "local_mirror_payload": local_mirror_payload,
    }
