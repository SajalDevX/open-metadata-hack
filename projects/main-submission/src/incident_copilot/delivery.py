import os

from incident_copilot.contracts import DeliveryResult
from incident_copilot.slack_sender import _render_slack_message, post_message


def deliver(brief, slack_sender, mirror_writer, store=None):
    slack_payload = {"channel": "slack", "brief": brief}
    local_mirror_payload = {"channel": "local_mirror", "brief": brief}
    mirror_writer(local_mirror_payload)

    incident_id = brief.get("incident_id", "unknown")
    slack_ok = False
    rendered = _render_slack_message({"brief": brief, "incident_id": incident_id})

    # Prefer bot-token path (returns ts for thread anchoring)
    if rendered and os.environ.get("SLACK_BOT_TOKEN"):
        channel = os.environ.get("SLACK_CHANNEL", "")
        ts = post_message(channel=channel, message=rendered)
        if ts:
            slack_ok = True
            if store:
                try:
                    store.save_thread_ts(incident_id, ts)
                except KeyError:
                    # incident not yet saved — persist brief first, then record ts
                    store.save_brief(brief, delivery_status="sent", primary_output="slack")
                    try:
                        store.save_thread_ts(incident_id, ts)
                    except KeyError:
                        pass  # still missing — ts will be orphaned

    # Fallback to webhook sender
    if not slack_ok and slack_sender is not None:
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
