# Demo Walkthrough — 3 depth levels

Pick based on audience and time:
- **60-second demo** (hallway pitch, judging first pass)
- **3-minute demo** (recorded video, deep session with judges)
- **5-minute demo** (full tour with governance + agent story)

All commands assume you're in `projects/main-submission/` and the service is running.

---

## Pre-flight (once, before recording)

```bash
cd /home/sajal/Desktop/hackathon/metadata/projects/main-submission

# 1. Ensure OpenMetadata is up
curl -sf http://localhost:8585/api/v1/system/version || { echo "Start OM: cd ~/om-local && docker compose up -d"; }

# 2. Ensure ngrok is still tunneling
curl -sf http://localhost:4040/api/tunnels | python3 -c "import sys,json; d=json.load(sys.stdin); print([t['public_url'] for t in d['tunnels']])"

# 3. Start (or confirm) the copilot
set -a && source .env && set +a
lsof -ti:8088 | xargs -r kill 2>/dev/null
python3 scripts/run_server.py > /tmp/copilot.log 2>&1 &
sleep 2
curl -s http://localhost:8088/health | python3 -m json.tool

# Expected: has_openmetadata: true · has_slack: true · has_ai: true
```

Open two browser tabs:
- Tab 1: Your Slack channel
- Tab 2: `http://localhost:8088/` (the copilot dashboard)

---

## 60-SECOND DEMO (hallway / first-pass judging)

### The narrative (15 s)

> "Data quality checks in OpenMetadata fail constantly — usually at 3 AM. The on-call engineer spends 15 minutes stitching together the test, lineage, ownership, and PII tags into a Slack message. This copilot does it in 3 seconds, with an audit trail."

### The action (45 s)

**1. Fire a realistic OpenMetadata alert** (paste this into terminal):

```bash
curl -X POST http://localhost:8088/webhooks/incidents \
  -H 'Content-Type: application/json' \
  -d '{
    "entity": {
      "id": "tc-demo-001",
      "fullyQualifiedName": "demo_mysql.customer_analytics.raw.customer_profiles",
      "testDefinition": {"name": "columnValueNullRatioExceeded"},
      "testCaseResult": {
        "testCaseStatus": "Failed",
        "result": "null ratio on customer_id exceeded 15% threshold"
      }
    }
  }'
```

**2. Switch to Slack** — the rich Block Kit brief has already arrived:
- Header: `✅ Incident om-tc-demo-001-... · allowed`
- 4 sections (What failed / What is impacted / Who acts first / What to do next)
- Acknowledge button

**3. Click Acknowledge** — ephemeral confirmation appears only for the clicker.

**4. Switch to dashboard tab** → refresh → incident row shows `delivery_status: acked_by:<you>`.

**Close out:** "Three seconds. Evidence-backed. Deterministic. 190 tests. Works offline with template fallbacks, better with the OpenRouter + OpenMetadata keys set."

---

## 3-MINUTE DEMO (recorded video / deep judging)

### Scene 1 — The problem (20 s)

> "When a DQ check fails at 3 AM, the on-call engineer needs four answers: what failed, what's impacted downstream, who owns it, and what to do next. That's 10 minutes of grunt work per incident — minimum."

Visual: show OpenMetadata UI at `http://localhost:8585` with the `customer_profiles` table you seeded earlier (it has PII.Sensitive tags).

### Scene 2 — Fire a real webhook (30 s)

```bash
curl -X POST http://localhost:8088/webhooks/incidents \
  -H 'Content-Type: application/json' \
  -d '{
    "entity": {
      "id": "tc-demo-realtime-1",
      "fullyQualifiedName": "demo_mysql.customer_analytics.raw.customer_profiles",
      "testDefinition": {"name": "columnValueNullRatioExceeded"},
      "testCaseResult": {
        "testCaseStatus": "Failed",
        "result": "null ratio on customer_id exceeded 15% threshold"
      }
    }
  }'
```

> "This is what OpenMetadata will send when a test fails. Watch Slack."

### Scene 3 — Slack message arrives (30 s)

Zoom into the Slack channel. Talk through the blocks:

> "Header tells me the incident ID and the policy state. **What failed** — Claude generated this specific narrative from the raw test signal, talking about the customer_id column and likely upstream cause. **Who acts first** — fallback chain went asset-owner → domain → team → channel. **Next steps** — AI-generated bullets tailored to the failure type."

### Scene 4 — Click a button (15 s)

Click **Acknowledge** in Slack.

> "One click. Ephemeral confirmation appears for me only — the original message stays in the channel so my team sees I took it. Server-side, the incident is now timestamped with my Slack identity. That's my audit trail."

### Scene 5 — HTML brief view (20 s)

Open `http://localhost:8088/incidents/om-tc-demo-realtime-1-.../view` (grab the real incident id from `http://localhost:8088/`).

> "Same canonical payload rendered as a one-page HTML report. This is what you attach to a post-mortem, embed in a Notion page, or send to a compliance auditor."

### Scene 6 — Dashboard (25 s)

Open `http://localhost:8088/`.

> "Every incident the copilot has handled. Policy badges show which ones needed steward approval. Delivery column shows who acknowledged what. This is your governance audit log — built for free as a side-effect of the triage flow."

### Scene 7 — Determinism (15 s)

```bash
./scripts/verify.sh
```

> "199 tests pass. The same input produces byte-identical output across runs — same md5 every time. No hidden state. That's critical when a judge wants to reproduce your demo."

### Scene 8 — Close (25 s)

> "Six hackathon problem statements covered in one system: RCA, DQ impact scoring, AI recommendations, Multi-MCP orchestrator, new MCP alert tools, and the Slack app. Runs with zero credentials, better with OpenRouter and OpenMetadata configured, best with Slack for the audit trail. Ships as a Docker compose. This is the missing layer between 'DQ test failed' and 'human decision made.'"

---

## 5-MINUTE DEMO (full tour)

Do everything from the 3-minute demo, then add these scenes:

### Scene 9 — The MCP angle (60 s)

> "This isn't just a service — it's an MCP server. Any agent framework can compose with it."

In another terminal:

```bash
python3 - <<'PY'
import sys; sys.path.insert(0, "src")
from incident_copilot.mcp_facade import get_rca_tool, score_impact_tool
import json

# Any agent can call this to get a cause-tree explanation
rca = get_rca_tool("tc-null-demo", "null_ratio_exceeded")
print(json.dumps(rca, indent=2))
PY
```

> "Four MCP tools — `triage_incident`, `score_impact`, `get_rca`, `notify_slack` — callable from Claude Desktop, Cursor, or your own LangChain orchestrator. When an agent is debugging a broken dashboard, it can ask the copilot for the structured impact analysis instead of re-implementing OpenMetadata lookups."

### Scene 10 — The governance angle (60 s)

Query the audit log:

```bash
curl -s http://localhost:8088/incidents | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f\"Total incidents: {d['count']}\n\")
for r in d['items'][:5]:
    status = r['delivery_status']
    marker = '🔴 UNACKED' if not status.startswith('acked_by:') else f'✅ {status}'
    print(f\"  {r['incident_id'][:40]:<40}  {r['policy_state']:<20}  {marker}\")
"
```

> "Monthly compliance review: one curl. Every PII-Sensitive incident, every approval, every denial, every ack, recorded with user and timestamp. Your auditor's dream."

### Scene 11 — Resilience (45 s)

Simulate a Slack outage:

```bash
# Break the webhook temporarily
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/INVALID/URL/0000
lsof -ti:8088 | xargs -r kill; sleep 1
set -a && source .env && set +a
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/INVALID/URL/0000 python3 scripts/run_server.py > /tmp/copilot.log 2>&1 &
sleep 2

# Fire an alert while Slack is down
curl -X POST http://localhost:8088/webhooks/incidents \
  -H 'Content-Type: application/json' \
  -d '{"entity":{"id":"tc-resilience","fullyQualifiedName":"demo_mysql.customer_analytics.raw.customer_profiles","testCaseResult":{"testCaseStatus":"Failed","result":"test"}}}'

# See it's queued for retry
curl -s http://localhost:8088/admin/retry-queue | python3 -m json.tool
```

> "Slack failed. Brief still rendered. Incident still persisted. Queued for retry. The background loop auto-retries every 30 seconds with backoff. If Slack stays down, the local mirror is the source of truth. No incident is ever lost."

---

## One-liner for a judge with no patience

```bash
./scripts/verify.sh && curl -X POST http://localhost:8088/webhooks/incidents \
  -H 'Content-Type: application/json' \
  -d '{"entity":{"id":"tc-judge","fullyQualifiedName":"demo_mysql.customer_analytics.raw.customer_profiles","testDefinition":{"name":"columnValueNullRatioExceeded"},"testCaseResult":{"testCaseStatus":"Failed","result":"null ratio on customer_id exceeded 15%"}}}' && xdg-open http://localhost:8088/
```

Runs: test suite (190 pass) → real webhook against OM → dashboard in browser. 15 seconds from cold to "proof it works."

---

## If something breaks mid-demo

| Symptom | Fast fix |
|---|---|
| `curl: connection refused` on 8088 | Copilot died — `cd projects/main-submission && python3 scripts/run_server.py` |
| "Port 8080 in use" | That's Airflow. Copilot uses 8088 — double-check `.env` |
| No Slack message | `curl http://localhost:8088/health` → check `has_slack: true`. If false, sourced `.env` in different shell |
| Button click does nothing visible | ngrok tunnel died — relaunch `ngrok http 8088`, update Request URL in Slack app |
| "fallback_reason_codes: OM_HTTP_FALLBACK_TO_FIXTURE" | `test_case_id` doesn't exist in OM — it's fine, the failure message still threads through. Show the narrative. |

---

## Assets to have open during the demo

1. **Terminal** with the copilot running (tail the log in another pane with `tail -f /tmp/copilot.log`)
2. **Terminal** for firing curl commands
3. **Browser tab** — Slack channel
4. **Browser tab** — `http://localhost:8088/` (dashboard)
5. **Browser tab** — `http://localhost:8585` (OpenMetadata UI, to ground the "real integration" claim)
6. **Editor** with `.env` NOT visible (it has secrets)
