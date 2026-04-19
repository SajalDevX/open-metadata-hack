import json
from incident_copilot.orchestrator import run_pipeline


def run_demo_once(live_event, replay_event, om_data=None):
    event = live_event if live_event else replay_event
    return run_pipeline(event, om_data, slack_sender=lambda _brief: False)


def run_replay_command(replay_event, om_data=None, output_path="runtime/local_mirror/latest_brief.json"):
    def mirror_writer(payload):
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        return output_path

    return run_pipeline(
        replay_event,
        om_data,
        slack_sender=lambda _brief: False,
        mirror_writer=mirror_writer,
    )
