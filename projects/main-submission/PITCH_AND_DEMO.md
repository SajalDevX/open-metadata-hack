# OpenMetadata Incident Copilot — What It Does & How to Demo It

## What this project does

### The problem in one sentence

When a data quality check fails in OpenMetadata, the on-call engineer has to
manually stitch together the test error, downstream lineage, ownership, and PII
rules into a Slack message — a 10–20 minute task that happens at 2 AM,
inconsistently, with no audit trail.

### What we built

**OpenMetadata Incident Copilot** is a service that wires directly into
OpenMetadata's alert webhook and turns any failed DQ check into a complete
triage brief — automatically, in under 5 seconds.

The brief answers the four questions every on-call engineer needs:

| Block | What it answers |
|---|---|
| **What failed** | Human-readable explanation of the failure (not raw jargon), with an AI-generated root-cause narrative |
| **What is impacted** | Downstream assets from OpenMetadata's lineage graph, scored by business criticality and PII exposure |
| **Who acts first** | Resolved owner chain: asset owner → domain owner → team → fallback channel |
| **What to do next** | Concrete next steps, adapted to whether the incident is allowed or requires governance approval |

The brief lands in Slack as a rich Block Kit message with interactive buttons
(Acknowledge / Approve / Deny). Every button click is HMAC-verified and written
to a SQLite audit log with the user's identity and timestamp. Same payload is
available as a JSON API and an HTML report.

The entire pipeline also exposes itself as **MCP tools**, so any AI agent (Claude
Desktop, your own LangChain bot, Cursor) can call `triage_incident`,
`score_impact`, `get_rca`, `notify_slack`, `suggest_tests_for_table`, or
`create_tests_in_om` directly — no re-implementing OpenMetadata lookups.

### What makes it different from a simple webhook forwarder

| Property | What it means in practice |
|---|---|
| **Deterministic policy** | PII.Sensitive tag on any impacted asset → `approval_required`. Always. Claude never decides governance. |
| **Evidence-linked** | Every claim links back to a real OM artifact. The brief shows `fallback_reason_codes` if data is missing — it never makes up names. |
| **Graceful degradation** | OpenRouter down → template narrative. OpenMetadata down → fixture fallback. Slack down → local mirror + auto-retry queue. Nothing blocks the pipeline. |
| **Full audit trail** | Every incident and every human action on it (who approved, when) is queryable. Ready for a SOC-2 reviewer. |
| **Composable via MCP** | Other agents can use the copilot's intelligence without rebuilding OM lookups. |

### What hackathon problems it covers

Six of the 22 OpenMetadata hackathon problem statements, in one product:

- **#26659** — Human-readable RCA for DQ failures
- **#26658** — DQ impact scoring with explainability
- **#26660** — AI-powered DQ test recommendations + writing them to OM
- **#26645** — Multi-MCP agent orchestrator
- **#26609** — New MCP alert and data insight tools
- **#26651** — Slack app for OpenMetadata

---

## How to run a great live demo

### What you need running before you start

```bash
# 1. OpenMetadata on :8585
curl -sf http://localhost:8585/api/v1/system/version

# 2. ngrok tunnel (needed for Slack button interactivity)
curl -sf http://localhost:4040/api/tunnels | python3 -c \
  "import sys,json; [print(t['public_url']) for t in json.load(sys.stdin)['tunnels']]"

# 3. The copilot on :8088
set -a && source .env && set +a
lsof -ti:8088 | xargs -r kill 2>/dev/null; sleep 1
python3 scripts/run_server.py > /tmp/copilot.log 2>&1 &
sleep 2
curl -s http://localhost:8088/health | python3 -m json.tool
# Look for: has_openmetadata: true · has_slack: true · has_ai: true
```

Have these open before you speak:

1. Terminal ready to paste curl commands
2. Browser tab — your Slack channel
3. Browser tab — `http://localhost:8088/` (the dashboard)
4. Browser tab — `http://localhost:8585` (OpenMetadata UI, to ground "real integration")

---

### The 90-second version (judging table / hallway)

**Say:**
> "Data quality checks in OpenMetadata fail constantly — usually at 3 AM. Right
> now the on-call engineer spends 15 minutes assembling a Slack message from the
> raw test error, the lineage graph, the owner records, and the PII tags. We do
> that in 3 seconds, with an audit trail."

**Do — paste this curl:**

```bash
curl -s -X POST http://localhost:8088/webhooks/incidents \
  -H 'Content-Type: application/json' \
  -d '{
    "entity": {
      "id": "tc-demo-live",
      "fullyQualifiedName": "demo_mysql.customer_analytics.raw.customer_profiles",
      "testDefinition": {"name": "columnValueNullRatioExceeded"},
      "testCaseResult": {
        "testCaseStatus": "Failed",
        "result": "null ratio on customer_id exceeded 15% threshold (observed 0.23)"
      }
    }
  }'
```

**Switch to Slack** — the message is already there. Walk through the four blocks
out loud. Point to the policy badge in the header (`approval_required` if the
table has PII.Sensitive tags). Click **Acknowledge**. Show the ephemeral
confirmation.

**Switch to the dashboard tab** — refresh — the row shows `acked_by:<you>`.

**Say:**
> "Three seconds. Evidence-backed. Deterministic policy. Audit trail built in.
> 245 tests pass. Works offline with template fallbacks — gets smarter with
> OpenMetadata and OpenRouter configured."

---

### The 4-minute version (recorded video / deep session)

#### Scene 1 — Ground the problem (30 s)

Show the OpenMetadata UI at `http://localhost:8585`. Navigate to the
`customer_profiles` table. Point at the PII.Sensitive column tags, the lineage
graph, the owner field.

> "Here's a real OpenMetadata instance with real data: PII-tagged columns,
> lineage edges to downstream dashboards, an assigned owner. When a test fails
> on this table the raw alert is one line of jargon. The on-call engineer
> manually walks this UI to build a Slack message. Let's see what happens when
> we plug in the copilot."

#### Scene 2 — Fire the webhook (20 s)

Paste the curl from above into your terminal. Say the command out loud so it
reads as intentional.

> "This is the POST that OpenMetadata sends when a test fails. I can also trigger
> it from the OM alert settings UI — but curl makes it obvious."

#### Scene 3 — Walk the Slack message (60 s)

Zoom into the Slack channel. Work through each block:

- **Header:** incident ID + policy badge. If it says `approval_required`, explain
  why: a PII.Sensitive-tagged asset is downstream.
- **What failed:** Claude turned the raw `"null ratio exceeded"` signal into a
  sentence a data engineer can actually read, with a root-cause category.
- **What is impacted:** the real lineage result from OM, scored by business
  criticality. Point out the `score_reason` logic if you have time.
- **Who acts first:** owner resolution chain — not hardcoded, pulled from OM.
- **What to do next:** policy-aware bullets. If approval is required, that's in
  the bullets. If not, it's a different set.

#### Scene 4 — Click a button (20 s)

Click **Approve** (or **Acknowledge**).

> "HMAC-signed POST hits our server via ngrok. We verify the signature — if a
> bad actor replays or forges this request, they get a 401. Otherwise we write
> `approved_by:<your-slack-id>` with the timestamp to SQLite. Private ephemeral
> confirmation appears for the clicker only — the channel message stays as a
> shared record."

#### Scene 5 — HTML report view (20 s)

Go to `http://localhost:8088/` → click the incident row → or go to
`/incidents/{id}/view`.

> "Same canonical payload, rendered as a one-page HTML report. Attach this to a
> post-mortem, drop it in Notion, email it to your compliance team. It's
> generated from the same JSON the Slack message was built from — same
> payload hash in both."

#### Scene 6 — MCP composability (30 s)

In a second terminal:

```bash
python3 - <<'PY'
import sys; sys.path.insert(0, "src")
from incident_copilot.mcp_facade import get_rca_tool, score_impact_tool
import json

rca = get_rca_tool("tc-null-demo", "null_ratio_exceeded")
print(json.dumps(rca, indent=2))
PY
```

> "This is the same logic as the webhook pipeline, but callable directly by any
> MCP client — Claude Desktop, your own LangChain bot, Cursor. The copilot
> exposes eight tools: triage, score, RCA, notify, suggest tests, create tests
> in OM, list recent failures, get table info. Other agents compose with it
> instead of re-implementing OpenMetadata lookups."

#### Scene 7 — Resilience & tests (20 s)

```bash
./scripts/verify.sh
```

> "245 tests pass. The verify script also confirms determinism: two runs of the
> same fixture produce byte-identical output — same md5 each time. Critical when
> a judge wants to reproduce the demo tomorrow."

---

### Things that make the demo land harder

**Show the failure message getting better.** If your `.env` has `OPENROUTER_API_KEY`
set, the narrative block is AI-generated and specific — it mentions the column
name, the threshold, and a likely upstream cause. If you kill the key, the
service still works with a template. Run the demo both ways back-to-back to
show graceful degradation.

**Use the PII path.** Make sure the table in your demo has a `PII.Sensitive`
column tag in OM. That triggers `approval_required` in the policy, which shows
the Approve/Deny buttons in Slack — the governance story lands much better when
you actually need to approve something.

**Show the retry queue recovering.** Kill the Slack webhook URL in your env,
fire a curl, show the incident persisting and the retry queue filling
(`GET /admin/retry-queue`), then restore the URL and hit `POST /admin/retry-now`.
This is the "resilience" story in 30 seconds.

**Have the audit query ready.** After a few incidents, run:

```bash
curl -s http://localhost:8088/incidents | python3 -c "
import sys, json
d = json.load(sys.stdin)
for r in d['items'][:5]:
    print(f\"{r['incident_id'][:38]:<38}  {r['policy_state']:<20}  {r['delivery_status']}\")
"
```

> "Every incident, every human decision on it. That's your governance audit log,
> built as a side-effect of the triage flow."

---

### If something breaks mid-demo

| Symptom | Fix |
|---|---|
| `connection refused` on 8088 | `python3 scripts/run_server.py` in project root |
| No Slack message appears | `curl http://localhost:8088/health` — check `has_slack: true`. Re-source `.env`. |
| Slack buttons do nothing | ngrok tunnel died — relaunch `ngrok http 8088`, update Request URL in Slack app settings |
| `approval_required` not showing | Table lacks `PII.Sensitive` tag in OM. Add it under the table's Tags tab. |
| `OM_HTTP_FALLBACK_TO_FIXTURE` in response | `entity_fqn` not found in OM — the failure message still threads through. Show the narrative, explain the fallback is intentional. |
| Port 8080 conflict | That's Airflow (bundled in OM's compose). Copilot runs on 8088 — check `.env`. |

---

### One-liner cold start for a skeptical judge

```bash
./scripts/verify.sh && \
curl -sX POST http://localhost:8088/webhooks/incidents \
  -H 'Content-Type: application/json' \
  -d '{"entity":{"id":"tc-judge","fullyQualifiedName":"demo_mysql.customer_analytics.raw.customer_profiles","testDefinition":{"name":"columnValueNullRatioExceeded"},"testCaseResult":{"testCaseStatus":"Failed","result":"null ratio on customer_id exceeded 15%"}}}' && \
xdg-open http://localhost:8088/
```

Runs 245 tests → fires a real webhook → opens the dashboard. 20 seconds, no
manual steps.
