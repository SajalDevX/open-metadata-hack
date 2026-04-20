# OpenMetadata Incident Copilot — Problem, Goals, Solution

## Executive summary

When a data quality check fails in OpenMetadata, the on-call engineer needs four
answers in a hurry: **what failed, what's impacted downstream, who owns it, and
what to do next** — especially when PII is involved and a data steward must
sign off before anyone touches the pipeline.

Today, stitching those answers together is a 10–20 minute manual exercise per
incident. At 2 AM, across many teams, with inconsistent Slack formats, no audit
trail, and no enforcement of governance rules.

This project is a **deterministic, read-only, AI-augmented copilot** that turns
one failed DQ check into a complete 4-block triage brief, delivered to Slack
with HMAC-signed interactive buttons, persisted as a queryable audit log,
composable over MCP — in under 5 seconds, unattended.

---

## 1. Problem statement

### 1.1 The failure mode we're fixing

A nightly DBT / Great Expectations / OpenMetadata profiler test fires against a
production table. It fails — say, `null_ratio(customer_id) > 15%`. What happens
next *today*:

1. OpenMetadata surfaces the failed check in its UI and (optionally) a generic
   email alert.
2. The on-call Data Reliability Engineer either catches the email (rare) or
   stumbles on it in the morning scan.
3. They open the OpenMetadata UI, find the test, read its raw error message
   (usually one line of jargon: `"null ratio exceeded threshold 0.15 (observed 0.23)"`).
4. They click into the table, walk the lineage graph by hand to find
   **downstream** assets (dashboards, ML feature stores, curated marts).
5. For each impacted asset they check:
   - Classification tags (is this PII?)
   - Ownership (who acts?)
   - Business-criticality (tier-1 dashboard or sandbox?)
6. They decide whether the fix needs steward sign-off (PII rules).
7. They write a Slack message from scratch summarising all of the above.
8. They @-mention the right people and wait.

**Time per incident: 10–20 minutes of repetitive grunt work.** At 2 AM.
Remembered from a runbook. Inconsistently formatted. No record kept.

### 1.2 What goes wrong because of this

| Failure mode | Business consequence |
|---|---|
| Alerts get ignored because the raw test error lacks context | Data bugs leak into BI dashboards and executive reports |
| Ownership is guessed from Slack handles, not from OM | Wrong person paged, delay compounds while the real owner sleeps |
| Governance (PII approval) is an informal "hey, is this cool?" Slack thread | No audit trail for SOC-2 / GDPR reviewers |
| Every team invents its own incident message format | Cross-team incidents descend into format-negotiation meta-discussion |
| Post-mortem is hard — no structured record of who decided what | Same incident class recurs; learnings don't compound |
| Juniors freeze when they see an alert they don't understand | Seniors get paged for things that should self-explain |

### 1.3 Who hurts

- **Data Reliability Engineers** (primary) — the 2 AM victims
- **Data Stewards / Governance Leads** — can't enforce PII rules without a signed audit
- **Data Platform Leads** — want one uniform incident format, have N
- **Compliance / auditors** — have no queryable log of DQ decisions
- **Engineering managers** — can't see incident-load patterns or owner response times

### 1.4 Hackathon problem statements this directly answers

The OpenMetadata hackathon board (project #107) lists 22 problem statements.
This project covers **six** of them in one coherent product:

| Problem # | Title | Covered by |
|---|---|---|
| [#26659](https://github.com/open-metadata/OpenMetadata/issues/26659) | Human-readable explanations and root-cause traces for DQ checks | `rca_engine.py` |
| [#26658](https://github.com/open-metadata/OpenMetadata/issues/26658) | Data Quality Checks Impact (scoring model + explainability) | `impact_scorer.py` |
| [#26660](https://github.com/open-metadata/OpenMetadata/issues/26660) | AI-Powered Data Quality Recommendations | `ai_recommender.py` |
| [#26645](https://github.com/open-metadata/OpenMetadata/issues/26645) | Multi-MCP Agent Orchestrator | `mcp_facade.py` + `mcp_transport_client.py` |
| [#26609](https://github.com/open-metadata/OpenMetadata/issues/26609) | New MCP Alert / Notification Tools | `mcp_facade.notify_slack` |
| [#26651](https://github.com/open-metadata/OpenMetadata/issues/26651) | Slack App for OpenMetadata | `slack_sender.py` + `slack_actions.py` |

---

## 2. Goals

We set these success criteria **before** we wrote a line of code:

### 2.1 Functional goals

1. **Sub-5-second triage brief.** From the moment OpenMetadata fires a webhook
   to the moment a Slack message lands in a team channel, total elapsed time
   must be under 5 seconds.
2. **Evidence-linked, not hallucinated.** Every claim in the brief must link
   back to an OpenMetadata artifact (test case ID, lineage edge, owner record,
   classification tag). The brief must be *reproducible*, not generative fiction.
3. **Deterministic policy decisions.** The rule "`PII.Sensitive` impact ⇒
   `approval_required`" must be a Python function, never a model prompt. The
   same input must always produce the same policy state.
4. **Graceful degradation.** If OpenRouter is down → use templates. If
   OpenMetadata is unreachable → use fixture fallback. If Slack is down → use
   local mirror and queue retry. **No single integration failure should block
   the triage flow.**
5. **Auditable.** Every incident, and every human action on it (ack / approve /
   deny), must be persisted with user identity and timestamp — queryable by an
   auditor without log-diving.
6. **Composable.** Other internal agents (Claude Desktop, LangChain orchestrators,
   custom bots) must be able to call the copilot's capabilities as MCP tools
   without re-implementing OpenMetadata lookups.

### 2.2 Non-functional goals

1. **TDD throughout.** Every feature lands with a failing test first, then a
   passing implementation, then a commit. Target: 150+ tests.
2. **Hybrid determinism.** Policy + scoring + routing = rule-based. Narrative
   text = AI-generated with template fallback. Never let the AI decide
   governance.
3. **Zero credentials required to demo.** The service must start and run
   end-to-end with no API keys — useful credentials unlock progressively better
   behaviour, never gate basic functionality.
4. **Ship as a single Docker image.** `docker compose up` is the deployment.
5. **Secret hygiene.** `.env` gitignored, signed webhook verification for
   interactive endpoints, never log secrets.

### 2.3 Out-of-scope (deliberately)

- Auto-remediation of failed data
- Running DQ checks (we react to them, not author them)
- Multi-incident correlation
- Free-form chat interface (that's the job of your MCP-connected agent)
- Replacing OpenMetadata (we sit on top of it)

---

## 3. The solution — architecture

### 3.1 One-paragraph description

The copilot is a **FastAPI service** that receives OpenMetadata alert webhooks,
runs them through an **11-block deterministic pipeline** that resolves context
from a **live OpenMetadata catalog** (direct HTTP or via OM's MCP server),
enriches the failure with an **AI-generated human-readable RCA narrative**
(Claude via OpenRouter, with template fallback), applies **deterministic impact
scoring and PII governance rules**, assembles a **canonical 4-block brief
payload**, and delivers it as a **Slack Block Kit message with HMAC-verified
interactive buttons** that record ack / approve / deny actions with full user
identity into a **SQLite audit log**. The same pipeline is exposed as four
**MCP tools** so any AI agent can compose with it.

### 3.2 The 11-block pipeline

```
Raw Event (OpenMetadata webhook or canonical envelope)
  │
  ▼
[1]  Adapter                  normalize to canonical envelope, preserve failure signal
  │
  ▼
[2]  Context Resolver         live OM HTTP / OM MCP / fixture fallback chain
  │
  ▼
[3]  Impact Prioritizer       bound lineage: depth ≤ 2, top ≤ 3, business-facing first
  │
  ▼
[9]  Impact Scorer            formula: business_facing×3 + pii×2 + 1/distance + log₂(dowstream+1)
  │                           every score ships with an explainable score_reason string
  ▼
[8]  RCA Engine               infer signal → cause tree → narrative
  │                           Claude via OpenRouter if key set, deterministic template otherwise
  ▼
[4]  Policy Advisor           hard rule: any PII.Sensitive in impact → approval_required
  │                           (Claude NEVER sees this step — policy is never AI-authored)
  ▼
[10] AI Recommender           Claude 2–3 bullets for "what to do next", policy-aware
  │                           falls back to static policy strings if Claude unavailable
  ▼
[5]  Brief Generator          canonical 4-block payload with per-block evidence refs
  │
  ▼
[6]  Delivery Layer           Slack Block Kit + local mirror JSON + HTML report
  │                           SHA-256 payload hash proves parity across surfaces
  ▼
[7]  Demo Harness             deterministic replay (md5-identical JSON across runs)

[11] MCP Facade              side-car exposing triage_incident, score_impact, get_rca, notify_slack
```

### 3.3 Surfaces and storage

Every successful pipeline run emits **identical canonical payloads** to up to
five surfaces:

| Surface | Purpose |
|---|---|
| Slack Block Kit message | Primary operator-facing output with interactive buttons |
| Local mirror JSON | Fallback when Slack fails, source of truth for audits |
| HTML report (`/incidents/{id}/view`) | Judge / post-mortem / compliance view |
| Terminal ANSI TUI | Demo / runbook rendering |
| SQLite `incidents` + `delivery_queue` | Persistence, retry, audit log |

Parity is enforced by a **SHA-256 payload hash** — the same hash appears in the
DB, the Slack message metadata, and the local mirror. Any surface divergence is
a bug, caught by tests.

### 3.4 Interactive governance flow

```
┌────────────────┐
│  DQ test fails │ on OpenMetadata
└────────┬───────┘
         │ webhook POST /webhooks/incidents
         ▼
┌─────────────────────────────────────────┐
│  Pipeline resolves → brief → Slack      │
│  Block Kit message with buttons         │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  On-call sees brief, clicks button      │
│  (Acknowledge / Approve / Deny)         │
└────────┬────────────────────────────────┘
         │ POST /slack/actions (HMAC-signed)
         ▼
┌─────────────────────────────────────────┐
│  Copilot verifies signature, records    │
│  action with user_id + timestamp.       │
│  Replies via chat.postEphemeral so      │
│  clicker sees private confirmation.     │
└─────────────────────────────────────────┘
```

Auditor can later query `/incidents` and get a complete record:

```json
{
  "incident_id": "om-tc-null-ratio-1",
  "policy_state": "approval_required",
  "delivery_status": "approved_by:alex-dre",
  "brief": { /* full canonical payload */ },
  "updated_at": 1713521400.12
}
```

---

## 4. How the solution hits each goal

### Goal 1 — Sub-5-second triage

**How:**
- FastAPI + uvicorn, single-process async webhook receiver
- SQLite with in-process connection (no network hop)
- OpenMetadata calls have 3-second timeouts with fallback
- OpenRouter calls have 3-second timeouts with fallback
- Slack POST is a single HTTP request (urllib)

**Evidence:** in local testing (see `docs/DEMO_WALKTHROUGH.md`), the webhook
`POST` returns in < 3 seconds end-to-end with a real Slack message landing in
the channel in the same window.

### Goal 2 — Evidence-linked, not hallucinated

**How:**
Each of the four brief blocks carries an `evidence_refs` list of
pointers back to OM artifacts:

```json
"what_failed": {
  "text": "Null ratio on customer_id exceeded 15% ...",
  "evidence_refs": ["incident_ref", "test_ref", "rca:null_ratio_exceeded"]
}
```

The RCA cause tree is a **deterministic lookup table** — AI only writes the
narrative on top. The impact list is the real OpenMetadata lineage result, not
model speculation. The owner is the real OM owner record. If these don't exist
in OM, the brief shows `fallback_reason_codes` like `MISSING_OWNER_METADATA`
rather than making up names.

### Goal 3 — Deterministic policy

**How:**
Policy is `incident_copilot/policy.py`, 20 lines of rule code:

```python
def evaluate_policy(incident_id, impacted_assets):
    has_pii = any(
        "PII.Sensitive" in (a.get("classifications") or [])
        for a in impacted_assets
    )
    if has_pii:
        return PolicyDecision(status="approval_required", ...)
    return PolicyDecision(status="allowed", ...)
```

The AI never sees this step. The brief's `policy_state` is set by this function
and passed to the AI as a read-only input — so the AI's recommendation bullets
can be policy-aware without being policy-authors.

### Goal 4 — Graceful degradation

**How:** fallback chains at every integration boundary, all tested:

| Integration | Failure path |
|---|---|
| OpenRouter | `Exception` or blank response → template narrative, brief still ships |
| OpenMetadata HTTP | `OpenMetadataClientError` → fixture payload, reason code `OM_HTTP_FALLBACK_TO_FIXTURE` |
| OpenMetadata MCP | `MCPTransportClientError` → HTTP fallback, reason code `OM_MCP_FALLBACK_TO_HTTP` |
| Slack webhook | Non-2xx → local mirror becomes primary, enqueue retry |
| SQLite | Same-process sqlite3, effectively cannot fail unless disk full |

Every failure emits a `fallback_reason_code` so an operator can see *why* a
field is empty without log-diving.

### Goal 5 — Auditable

**How:**
- SQLite `incidents` table: `(incident_id, policy_state, delivery_status, primary_output, payload_hash, brief_json, created_at, updated_at)`
- Every button click writes `delivery_status = "acked_by:alex"` / `"approved_by:alex"` / `"denied_by:alex"`
- HMAC signature verification on `/slack/actions` prevents forged actions
- Payload SHA-256 hash written alongside the brief catches any tampering
- `GET /incidents?limit=500` returns the entire audit log as JSON; `GET /incidents/{id}/view` renders it as an HTML report

**Evidence:** test suite `tests/test_slack_actions.py` proves:
- Valid HMAC → 200 + status update
- Invalid HMAC → 401
- Stale timestamp (> 5 min) → 401 (replay protection)

### Goal 6 — Composable via MCP

**How:** `src/incident_copilot/mcp_facade.py` exposes four MCP tools via
`FastMCP`:

| Tool | Signature |
|---|---|
| `triage_incident(incident_id, entity_fqn)` | Run full pipeline → return canonical brief |
| `score_impact(entity_fqn, lineage_depth)` | Return scored asset list with `score_reason` |
| `get_rca(test_case_id, signal_type)` | Return cause tree + narrative |
| `notify_slack(incident_id, brief)` | Post to Slack + return SHA-256 payload hash |

Any MCP client (Claude Desktop, `mcp-cli`, your own LangChain) can call these
without re-implementing OpenMetadata lookups. The MCP transport also goes the
other way — `mcp_transport_client.py` lets the copilot *consume* OpenMetadata's
MCP server for context resolution.

### Non-functional goals

- **TDD throughout:** every commit in the git log follows the pattern `test →
  implementation → commit`. Verified by reading the commit history.
- **Hybrid determinism:** `policy.py`, `impact_scorer.py`, `owner_routing.py`,
  `impact.py` — all pure-function deterministic. `rca_engine.py`,
  `ai_recommender.py` — have hybrid paths with template fallback. Never the
  reverse.
- **Zero-credential demo:** `./scripts/verify.sh` runs the full suite + a
  fixture-backed incident → 4-block brief with no API keys needed.
- **Docker image:** `docker compose up --build` fully stands up the service.
- **Secret hygiene:** `.gitignore` covers `.env`, `*.pem`, `*.key`, and the
  SQLite DB file. `/slack/actions` verifies HMAC on every request.

---

## 5. Live end-to-end proof

### 5.1 What's running right now

- **OpenMetadata 1.12.0** on `http://localhost:8585` with a real table
  (`demo_mysql.customer_analytics.raw.customer_profiles`), PII-Sensitive column
  tags, a downstream lineage edge, and an assigned owner
- **Incident Copilot** on `http://localhost:8088` with FastAPI +
  `uvicorn` + background retry loop + OM poller ready
- **Slack workspace** `open-meta-data` with app `Incident Copilot` using:
  - Incoming webhook for posting briefs
  - Interactivity endpoint → ngrok → `/slack/actions`
  - Bot OAuth token for `chat.postEphemeral` private confirmations
- **OpenRouter** with a live API key, routing to `anthropic/claude-haiku-4-5`

### 5.2 What the demo produces

A single curl against `/webhooks/incidents` with a realistic failure payload
produces, within 3 seconds:

1. **In Slack:** a Block Kit message with the policy badge, 4 sections, and
   three buttons (Acknowledge · Approve · Deny) — buttons are visible only
   when `policy_state = approval_required`
2. **On the dashboard** (`http://localhost:8088/`): a new row showing the
   incident ID, policy state, truncated failure summary, delivery status, and
   last-updated time
3. **At `GET /incidents/{id}`:** the full canonical brief payload as JSON
4. **At `GET /incidents/{id}/view`:** a styled HTML one-page report
5. **In SQLite:** a persisted row with `payload_hash` for later audit

Clicking **Approve** in Slack:
1. Sends HMAC-signed POST to `/slack/actions` via ngrok
2. Copilot verifies signature, fetches the incident, updates
   `delivery_status = "approved_by:thehackertimes2k23"` in SQLite
3. Posts a private ephemeral confirmation back via `chat.postEphemeral`
4. Dashboard row updates on next refresh

### 5.3 Test coverage as of current HEAD

```
199 tests pass — pytest tests/ -q

covering:
  adapter, ai_recommender, app (+ retry), background_retry, brief,
  brief_renderer, config, context_resolver, contracts, dashboard,
  delivery, delivery_queue, demo_harness, impact, impact_scorer,
  live_validation, mcp_facade, mcp_transport_client, om_poller,
  openmetadata_client, openrouter_client, orchestrator, owner_routing,
  policy, rca_engine, slack_actions, slack_sender, startup_validator,
  store, terminal_renderer, webhook_parser
```

---

## 6. What's deliberately unfinished

Documented in `docs/KNOWN_GAPS.md`. Summary:

- Webhook endpoint requires signed requests via `COPILOT_WEBHOOK_SECRET`
- Retry-queue dead letters stay in the DB after max attempts (no viewer UI)
- Container runs as default Python user (no custom non-root hardening)
- Multi-incident correlation explicitly out of scope

None of these affect the core "real-time single-incident triage" value
proposition. They're hardening tasks for a production rollout, not architectural
debt.

---

## 7. One-sentence pitches

For different audiences, pick one:

**To a data engineer:**
> "Every failed DQ check becomes a reproducible, evidence-backed Slack brief
> with an audit trail — in under 5 seconds, without a human."

**To a CTO:**
> "The missing layer between 'DQ test failed' and 'human decision made',
> enforcing governance rules and generating compliance-ready audit logs as a
> side effect."

**To a judge:**
> "Six hackathon problem statements, one coherent product — deterministic
> scoring, AI-augmented narratives, HMAC-signed Slack interactivity, MCP
> composability, 190 tests, Docker-packaged, works offline with template
> fallbacks."

**To an engineering manager:**
> "Stop your on-call team from rebuilding the same Slack message from
> scratch at 2 AM."

---

## 8. Repo artifacts supporting this document

- `README.md` — quickstart and endpoint map
- `docs/INTEGRATION_SETUP.md` — credential sources (OM / Slack / OpenRouter)
- `docs/OPENMETADATA_ALERT_SETUP.md` — wiring OM → copilot webhook
- `docs/DEMO_WALKTHROUGH.md` — 60-second / 3-minute / 5-minute demo scripts
- `docs/TESTING.md` — 8 depth-ordered ways to exercise the product
- `docs/KNOWN_GAPS.md` — deferred items and known limitations
- `docs/DEMO_SCRIPT.md` — video recording narration
- `../../2026-04-18-metadata-incident-copilot-design.md` — base architecture spec
- `../../2026-04-18-metadata-incident-copilot-expanded-design.md` — full 11-block design
- `../../2026-04-18-metadata-incident-copilot-expanded-plan.md` — TDD implementation plan

190 tests, 35+ commits, zero secrets in git, deterministic demo. Ship it.
