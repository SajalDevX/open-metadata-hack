import os

from incident_copilot.contracts import DeliveryResult
from incident_copilot.slack_sender import _render_slack_message, post_message


def deliver(brief, slack_sender, mirror_writer, store=None):
    slack_payload = {"channel": "slack", "brief": brief}
    local_mirror_payload = {"channel": "local_mirror", "brief": brief}
    mirror_writer(local_mirror_payload)

    slack_ok = False
    if slack_sender is None:
        # Bot-token path: use post_message which returns a ts string on success
        channel = os.environ.get("SLACK_CHANNEL", "")
        message = _render_slack_message(slack_payload)
        if message and channel:
            ts = post_message(channel=channel, message=message)
            if ts:
                slack_ok = True
                if store is not None:
                    incident_id = brief.get("incident_id")
                    if incident_id:
                        # Ensure the record exists before saving the ts
                        if store.fetch_by_id(incident_id) is None:
                            store.save_brief(
                                brief,
                                delivery_status="sent",
                                primary_output="slack",
                            )
                        store.save_thread_ts(incident_id, ts)
    else:
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
