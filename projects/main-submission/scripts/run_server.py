#!/usr/bin/env python3
"""Run the live incident copilot service via uvicorn."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import uvicorn

from incident_copilot.app import create_app
from incident_copilot.config import load_config
from incident_copilot.startup_validator import validate_startup


def main():
    cfg = load_config()
    report = validate_startup(cfg)
    for err in report.errors:
        print(f"  ERROR: {err}")
    for warn in report.warnings:
        print(f"  warn:  {warn}")
    if not report.ok:
        print("Aborting due to config errors above.")
        raise SystemExit(2)

    app = create_app(cfg)
    print(f"Starting incident-copilot service on http://{cfg.host}:{cfg.port}")
    print(f"  DB:            {cfg.db_path}")
    print(f"  OpenMetadata:  {'connected' if cfg.has_openmetadata else 'not configured'}")
    print(f"  Slack:         {'connected' if cfg.has_slack else 'not configured'}")
    print(f"  AI narratives: {'enabled' if cfg.has_ai else 'template fallback'}")
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="info")


if __name__ == "__main__":
    main()
