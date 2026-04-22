# Metadata Incident Copilot

A deterministic, evidence-backed **data-quality incident triage copilot** for OpenMetadata. Turns a single failed DQ check into a 4-block brief that answers:

> **What failed · What is impacted · Who acts first · What to do next**

Designed for a 2–5 minute hackathon demo. Every answer is linked back to OpenMetadata evidence (incident, test, lineage, ownership, classification), and every AI call has a deterministic fallback so the demo never breaks.

---

## Problem

When a DQ check fails, a Data Reliability Engineer has to hand-stitch:

1. **What** test failed and what the data signal means.
2. **Downstream impact** — which tables, pipelines, dashboards break.
3. **Who** should act first — asset owner, domain owner, team, or fallback channel.
4. **What to do next** — especially when PII is involved and a data steward must approve.

This copilot does that in one deterministic pass.

---

## What it covers (OpenMetadata Hackathon problem statements)

| Problem | Issue | Component |
|---|---|---|
| Human-readable RCA explanations | [#26659](https://github.com/open-metadata/OpenMetadata/issues/26659) | `rca_engine.py` |
| DQ Checks Impact scoring | [#26658](https://github.com/open-metadata/OpenMetadata/issues/26658) | `impact_scorer.py` |
| AI-Powered DQ Recommendations | [#26660](https://github.com/open-metadata/OpenMetadata/issues/26660) | `ai_recommender.py` |
| Multi-MCP Agent Orchestrator | [#26645](https://github.com/open-metadata/OpenMetadata/issues/26645) | `mcp_facade.py` + `mcp_transport_client.py` |
| New MCP Alert/Notification Tools | [#26609](https://github.com/open-metadata/OpenMetadata/issues/26609) | `mcp_facade.notify_slack` |
| Slack App for OpenMetadata | [#26651](https://github.com/open-metadata/OpenMetadata/issues/26651) | `slack_sender.py` |

---

## Architecture (11 blocks)

```
Raw Incident Event
  → [1]  Adapter                   normalize into canonical envelope
  → [2]  Context Resolver          live OM HTTP / OM MCP / fixture fallback chain
  → [3]  Impact Prioritizer        bound lineage (depth ≤ 2, top ≤ 3)
  → [9]  Impact Scorer             deterministic explainable score formula
  → [8]  RCA Engine                signal → cause tree → narrative (AI + template)
  → [4]  Policy Advisor            PII.Sensitive → approval_required
  → [10] AI Recommender            Claude bullets for "what to do next"
  → [5]  Brief Generator           canonical 4-block brief payload
  → [6]  Delivery Layer            Slack webhook + local mirror
  → [7]  Demo Harness              deterministic replay

  [11]   MCP Facade                exposes 4 MCP tools + consumes OM MCP
```

All AI calls (blocks 8, 10) go through **OpenRouter** (`openai` SDK with `anthropic/claude-haiku-4-5`). If `OPENROUTER_API_KEY` is unset — or if any Claude call fails or times out — deterministic template strings are used. **No blank brief fields, ever.**

---

## Quick start

### Option A — Docker (recommended)

```bash
cd projects/main-submission
cp .env.example .env        # edit to taste; webhook ingress needs COPILOT_WEBHOOK_SECRET
docker compose up --build
```

Dashboard: http://localhost:8080 · Webhook endpoint: http://localhost:8080/webhooks/incidents

### Option B — Live service, direct Python

```bash
cd projects/main-submission
python3 -m pip install --user pytest openai fastmcp fastapi uvicorn httpx
python3 scripts/run_server.py
```

### Option C — One-shot demo (no server, no OpenMetadata)

```bash
cd projects/main-submission
python3 scripts/run_demo.py \
  --replay runtime/fixtures/replay_event.json \
  --context runtime/fixtures/replay_om_context.json \
  --output runtime/local_mirror/latest_brief.json
```

Outputs:
- **Terminal:** colour-coded 4-block brief printed to stdout.
- **JSON:** `runtime/local_mirror/latest_brief.json` — canonical payload (same hash on every run).
- **HTML:** `runtime/local_mirror/latest_brief.html` — judge-ready visual report.

### 3. Verify everything in one shot

```bash
cd projects/main-submission
./scripts/verify.sh
```

Runs: full test suite → demo → determinism hash check → Python smoke test → MCP tool sanity check.

---

## Enabling live OpenMetadata

Set env vars and swap the flag on the demo script:

```bash
export OPENMETADATA_BASE_URL="http://localhost:8585/api"
export OPENMETADATA_JWT_TOKEN="eyJ..."          # from Bots → Ingestion Bot
cd projects/main-submission

# Direct HTTP (OpenMetadata REST API)
python3 scripts/run_demo.py --replay runtime/fixtures/replay_event.json \
  --output runtime/local_mirror/latest_brief.json --use-live-om

# OR via OpenMetadata's MCP server (falls back to HTTP automatically)
export OPENMETADATA_MCP_URL="http://localhost:8787/mcp"
python3 scripts/run_demo.py --replay runtime/fixtures/replay_event.json \
  --output runtime/local_mirror/latest_brief.json --use-om-mcp
```

Fallback chain: `MCP → HTTP → fixture payload`. Every fallback gets a reason code in the brief.

---

## Enabling Slack delivery

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T.../B.../..."
cd projects/main-submission
python3 scripts/run_demo.py --replay ... --context ... --output ...
```

If the webhook fails, `local_mirror` becomes the primary output — payload hash parity preserved between Slack and local mirror.

---

## Enabling AI narratives (optional)

```bash
export OPENROUTER_API_KEY="sk-or-..."
cd projects/main-submission
python3 scripts/run_demo.py --replay ... --context ... --output ...
```

With the key set, the RCA narrative and "what to do next" bullets come from Claude via OpenRouter. Without it, deterministic templates are used. The demo works either way.

---

## Running as an MCP server

```bash
cd projects/main-submission
python3 src/incident_copilot/mcp_facade.py
```

Exposes 4 MCP tools callable from Claude Desktop, `mcp-cli`, or any MCP client:

| Tool | Purpose |
|---|---|
| `triage_incident(incident_id, entity_fqn)` | Full pipeline → canonical 4-block brief |
| `score_impact(entity_fqn, lineage_depth)` | Ranked scored assets with `score_reason` |
| `get_rca(test_case_id, signal_type)` | Cause tree + narrative for a signal |
| `notify_slack(incident_id, brief)` | Post to Slack; returns payload hash |

---

## Determinism & demo safety

- Every brief payload is stable — repeated runs produce byte-identical JSON (`md5sum` proves it in `verify.sh`).
- Policy decisions (`PII.Sensitive → approval_required`) are **never** made by Claude — only by the rule-based Policy Advisor.
- Impact scoring is a pure formula: `business_facing×3 + pii_sensitive×2 + 1/distance + log2(downstream+1)`.
- Every score ships with an explainable `score_reason` string — matches #26658 judging criteria.
- Claude calls have a 3-second timeout and silent template fallback.
- If Slack delivery fails, local mirror becomes primary and parity is verified by SHA-256 payload hash.

---

## Project layout

```
projects/main-submission/
├── src/incident_copilot/
│   ├── adapter.py                   [1] event normalization
│   ├── context_resolver.py          [2] live HTTP + MCP + fixture fallback
│   ├── impact.py                    [3] bounded prioritizer
│   ├── impact_scorer.py             [9] explainable deterministic scoring
│   ├── rca_engine.py                [8] signal → cause tree → narrative
│   ├── policy.py                    [4] PII.Sensitive → approval_required
│   ├── ai_recommender.py            [10] Claude bullets + fallback
│   ├── brief.py                     [5] canonical 4-block payload
│   ├── delivery.py                  [6] Slack + local mirror + degraded mode
│   ├── orchestrator.py              pipeline wiring
│   ├── demo_harness.py              [7] deterministic replay
│   ├── mcp_facade.py                [11] FastMCP server exposing 4 tools
│   ├── mcp_transport_client.py      consume OpenMetadata MCP
│   ├── openmetadata_client.py       direct HTTP client for REST API
│   ├── slack_sender.py              real webhook POST
│   ├── openrouter_client.py         OpenAI-SDK → OpenRouter
│   ├── brief_renderer.py            HTML report
│   └── terminal_renderer.py         ANSI terminal report
├── tests/                           pytest suite (100+ tests)
├── runtime/
│   ├── fixtures/                    deterministic replay fixtures
│   └── local_mirror/                output JSON + HTML
└── scripts/
    ├── run_demo.py                  one-click entry point
    └── verify.sh                    full verification in one shot
```

---

## Live service endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | HTML dashboard — recent incidents + integration status |
| POST | `/webhooks/incidents` | Receive OpenMetadata alert payloads |
| GET | `/incidents` | List recent briefs (JSON) |
| GET | `/incidents/{id}` | Full brief payload (JSON) |
| GET | `/incidents/{id}/view` | Rendered HTML brief |
| POST | `/slack/actions` | Slack interactivity (ack/approve/deny) — HMAC-verified |
| GET | `/health` | Liveness + which integrations are configured |
| GET | `/metrics` | `{incident_count, pending_retries}` |
| GET | `/admin/retry-queue` | Inspect Slack retry queue |
| POST | `/admin/retry-now` | Force immediate retry sweep |

## Deployment docs

- `projects/main-submission/docs/INTEGRATION_SETUP.md` — where to get OpenMetadata / Slack / OpenRouter credentials
- `projects/main-submission/docs/OPENMETADATA_ALERT_SETUP.md` — step-by-step for pointing OM at the webhook
- `projects/main-submission/docs/TESTING.md` — 8 depth-ordered ways to test the product
- `projects/main-submission/docs/KNOWN_GAPS.md` — deferred items + verified-working inventory
- `projects/main-submission/docs/DEMO_SCRIPT.md` — 2-minute demo recording guide
- `projects/main-submission/.env.example` — every supported env var documented

## Design docs

- `2026-04-18-metadata-incident-copilot-expanded-design.md` — expanded design (AI + MCP + scoring)
- `2026-04-18-metadata-incident-copilot-expanded-plan.md` — expanded implementation plan
