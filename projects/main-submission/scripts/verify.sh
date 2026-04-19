#!/usr/bin/env bash
# One-shot verification: runs tests, demo, determinism check, and smoke test.
set -e

cd "$(dirname "$0")/.."

PASS="\033[32m✓\033[0m"
FAIL="\033[31m✗\033[0m"
BOLD="\033[1m"
DIM="\033[2m"
RESET="\033[0m"

section() { echo; echo -e "${BOLD}━━━ $1 ━━━${RESET}"; }

section "1. Full test suite"
python3 -m pytest tests/ -q
echo -e "${PASS} all tests pass"

section "2. One-click demo"
python3 scripts/run_demo.py \
  --replay runtime/fixtures/replay_event.json \
  --context runtime/fixtures/replay_om_context.json \
  --output runtime/local_mirror/latest_brief.json
echo -e "${PASS} demo completed"

section "3. Determinism check (two runs, hash compare)"
python3 scripts/run_demo.py \
  --replay runtime/fixtures/replay_event.json \
  --context runtime/fixtures/replay_om_context.json \
  --output runtime/local_mirror/run_a.json > /dev/null
python3 scripts/run_demo.py \
  --replay runtime/fixtures/replay_event.json \
  --context runtime/fixtures/replay_om_context.json \
  --output runtime/local_mirror/run_b.json > /dev/null
HASH_A=$(md5sum runtime/local_mirror/run_a.json | awk '{print $1}')
HASH_B=$(md5sum runtime/local_mirror/run_b.json | awk '{print $1}')
echo -e "${DIM}run A: $HASH_A${RESET}"
echo -e "${DIM}run B: $HASH_B${RESET}"
if [ "$HASH_A" = "$HASH_B" ]; then
  echo -e "${PASS} determinism verified"
  rm -f runtime/local_mirror/run_a.json runtime/local_mirror/run_b.json
else
  echo -e "${FAIL} determinism BROKEN — hashes differ"
  exit 1
fi

section "4. Smoke test — pipeline from Python"
python3 - <<'PY'
import sys, json
sys.path.insert(0, "src")
from incident_copilot.orchestrator import run_pipeline

event = json.load(open("runtime/fixtures/replay_event.json"))
ctx = json.load(open("runtime/fixtures/replay_om_context.json"))
out = run_pipeline(event, ctx, slack_sender=lambda _: False)

print(f"Incident:       {out['brief']['incident_id']}")
print(f"Policy:         {out['brief']['policy_state']}")
print(f"RCA signal:     {out['rca'].signal_type}")
print(f"RCA source:     {out['rca'].narrative_source}")
print(f"RCA narrative:  {out['rca'].narrative}")
print(f"Top asset:      {out['scored_assets'][0].fqn}  score={out['scored_assets'][0].score}")
print(f"Reason:         {out['scored_assets'][0].score_reason}")
print(f"Recommendation source: {out['recommendation'].source}")
for b in out['recommendation'].bullets:
    print(f"  • {b}")
PY
echo -e "${PASS} pipeline smoke test"

section "5. MCP facade tools (direct call, no server)"
python3 - <<'PY'
import sys
sys.path.insert(0, "src")
from incident_copilot.mcp_facade import get_rca_tool, score_impact_tool, notify_slack_tool

r = get_rca_tool("tc-null-1", "null_ratio_exceeded")
print(f"get_rca:       {r['signal_type']} → {r['cause_tree']}")
print(f"score_impact:  {score_impact_tool('svc.db.orders')}")
print(f"notify_slack:  {notify_slack_tool('inc-1')}")
PY
echo -e "${PASS} MCP tools callable"

section "Summary"
if [ -n "$OPENROUTER_API_KEY" ]; then
  echo -e "${DIM}OPENROUTER_API_KEY is set — Claude narratives active${RESET}"
else
  echo -e "${DIM}OPENROUTER_API_KEY not set — deterministic template fallback active${RESET}"
fi
echo -e "${PASS} ${BOLD}all checks passed${RESET}"
