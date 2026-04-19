#!/usr/bin/env python3
"""One-click demo entrypoint — replays deterministic incident + OM context fixtures."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from incident_copilot.demo_harness import run_replay_command


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", required=True, help="Path to replay event JSON")
    parser.add_argument("--context", required=True, help="Path to OM context JSON")
    parser.add_argument("--output", required=True, help="Path for local mirror output")
    args = parser.parse_args()

    replay_event = json.loads(Path(args.replay).read_text(encoding="utf-8"))
    om_data = json.loads(Path(args.context).read_text(encoding="utf-8"))

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    result = run_replay_command(replay_event, om_data, args.output)

    print(f"Incident: {result['brief']['incident_id']}")
    print(f"Policy: {result['brief']['policy_state']}")
    print(f"Delivery primary: {result['delivery']['delivery'].primary_output}")
    print(f"Brief written to: {args.output}")


if __name__ == "__main__":
    main()
