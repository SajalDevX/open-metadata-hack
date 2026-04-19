#!/usr/bin/env python3
"""One-click demo entrypoint — replays deterministic incident + OM context fixtures."""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from incident_copilot.brief_renderer import render_brief_html
from incident_copilot.demo_harness import run_replay_command


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", required=True, help="Path to replay event JSON")
    parser.add_argument("--context", help="Path to OM context JSON (required unless --use-live-om)")
    parser.add_argument("--output", required=True, help="Path for local mirror output")
    parser.add_argument(
        "--use-live-om",
        action="store_true",
        help="Resolve context from a live OpenMetadata server (uses OPENMETADATA_* env vars).",
    )
    parser.add_argument(
        "--use-om-mcp",
        action="store_true",
        help="Use the MCP mode path for context resolution (falls back to HTTP bridge by default).",
    )
    parser.add_argument(
        "--openmetadata-base-url",
        help="Optional OpenMetadata base URL override, e.g. http://localhost:8585/api",
    )
    parser.add_argument(
        "--openmetadata-jwt-token",
        help="Optional OpenMetadata JWT token override.",
    )
    args = parser.parse_args()

    replay_event = json.loads(Path(args.replay).read_text(encoding="utf-8"))
    om_data = None
    if args.context:
        om_data = json.loads(Path(args.context).read_text(encoding="utf-8"))
    elif not args.use_live_om:
        parser.error("--context is required unless --use-live-om is set")

    if args.openmetadata_base_url:
        os.environ["OPENMETADATA_BASE_URL"] = args.openmetadata_base_url
    if args.openmetadata_jwt_token:
        os.environ["OPENMETADATA_JWT_TOKEN"] = args.openmetadata_jwt_token
    if args.use_live_om:
        os.environ["OM_CONTEXT_SOURCE"] = "direct_http"
    if args.use_om_mcp:
        os.environ["USE_OM_MCP"] = "true"

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    result = run_replay_command(replay_event, om_data, args.output)

    html_path = Path(args.output).with_suffix(".html")
    html_path.write_text(render_brief_html(result["brief"]), encoding="utf-8")

    print(f"Incident: {result['brief']['incident_id']}")
    print(f"Policy: {result['brief']['policy_state']}")
    print(f"Delivery primary: {result['delivery']['delivery'].primary_output}")
    print(f"Brief JSON: {args.output}")
    print(f"Brief HTML: {html_path}")


if __name__ == "__main__":
    main()
