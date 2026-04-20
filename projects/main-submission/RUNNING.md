# How to Run the OpenMetadata Incident Copilot

Everything you need to get the service running — from zero to a live demo with
Slack, OpenMetadata, and AI narratives.

---

## Table of contents

1. [Prerequisites](#1-prerequisites)
2. [Clone and install](#2-clone-and-install)
3. [Configure environment variables](#3-configure-environment-variables)
4. [Run the service](#4-run-the-service)
5. [Verify it works](#5-verify-it-works)
6. [Connect OpenMetadata](#6-connect-openmetadata)
7. [Connect Slack](#7-connect-slack)
8. [Enable AI narratives (OpenRouter)](#8-enable-ai-narratives-openrouter)
9. [Run via Docker](#9-run-via-docker)
10. [Endpoint reference](#10-endpoint-reference)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.12+ | Check with `python3 --version` |
| pip | any recent | bundled with Python |
| Docker + Docker Compose | any v2 | only needed for the Docker path |
| ngrok | any | only needed to receive Slack button clicks on localhost |

You do **not** need OpenMetadata, Slack, or an AI key to start the service.
Those integrations unlock more functionality progressively — see the matrix in
section 3.

---

## 2. Clone and install

```bash
git clone <repo-url>
cd metadata/projects/main-submission

# Create a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"
```

If you don't have a `[dev]` extras group, plain `pip install -e .` works —
the dev extras just add `pytest`.

Create the runtime directory the service writes its SQLite DB into:

```bash
mkdir -p runtime
```

---

## 3. Configure environment variables

Copy the example file:

```bash
cp .env.example .env
```

Open `.env` in your editor. The full set of variables:

```bash
# ── Service (required for non-default config) ──────────────────────────
COPILOT_HOST=0.0.0.0
COPILOT_PORT=8088          # default 8080; change if something else owns that port
COPILOT_DB_PATH=runtime/incidents.db
COPILOT_DEFAULT_CHANNEL=#metadata-incidents

# ── OpenMetadata ────────────────────────────────────────────────────────
OPENMETADATA_BASE_URL=http://localhost:8585/api
OPENMETADATA_JWT_TOKEN=eyJraWQi...   # bot JWT — see section 6

# ── Webhook auth (optional hardening) ──────────────────────────────────
# When set, POST /webhooks/incidents requires: Authorization: Bearer <value>
# Leave unset to accept unauthenticated webhooks (fine behind a VPN).
# WEBHOOK_SECRET=some-random-string

# ── Slack ───────────────────────────────────────────────────────────────
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...
SLACK_SIGNING_SECRET=abc123...       # only needed for interactive buttons
SLACK_BOT_TOKEN=xoxb-...            # only needed for ephemeral replies

# ── AI narratives ───────────────────────────────────────────────────────
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=anthropic/claude-haiku-4-5   # default; any OpenRouter model works

# ── Optional: event polling instead of webhooks ─────────────────────────
# COPILOT_ENABLE_POLLER=true
# COPILOT_POLLER_INTERVAL_SECONDS=60
```

**None of these are required.** The service starts and runs a full pipeline
with zero env vars set — it falls back to fixture data and template narratives.

### Minimum-to-try matrix

| What you have | What you get |
|---|---|
| Nothing | Full pipeline using fixture data. Template narratives. `verify.sh` passes. |
| `+ OPENROUTER_API_KEY` | AI-generated RCA narratives and recommendation bullets. |
| `+ OPENMETADATA_BASE_URL + OPENMETADATA_JWT_TOKEN` | Live context resolution — real lineage, real owners, real tags. |
| `+ SLACK_WEBHOOK_URL` | Briefs arrive in your Slack channel as Block Kit messages. |
| `+ SLACK_SIGNING_SECRET + ngrok` | Acknowledge / Approve / Deny buttons become interactive. Audit log records user + timestamp. |

---

## 4. Run the service

### Option A — direct Python (recommended for development)

```bash
# From projects/main-submission/
set -a && source .env && set +a
python3 scripts/run_server.py
```

Expected startup output:

```
Starting incident-copilot service on http://0.0.0.0:8088
  DB:            runtime/incidents.db
  OpenMetadata:  connected          ← or "not configured"
  Slack:         connected          ← or "not configured"
  AI narratives: enabled            ← or "template fallback"
INFO:     Application startup complete.
```

The service runs in the foreground. Use a second terminal for everything else.
To run in background and tail logs:

```bash
python3 scripts/run_server.py > /tmp/copilot.log 2>&1 &
tail -f /tmp/copilot.log
```

### Option B — Docker Compose

```bash
# From projects/main-submission/
# Make sure .env is populated first
docker compose up --build
```

The service runs on `http://localhost:8080` (container port 8080 mapped to
host port 8080 — set `COPILOT_PORT=8080` in `.env`).

To run detached:

```bash
docker compose up --build -d
docker compose logs -f
```

To stop:

```bash
docker compose down
```

Data persists in the `copilot-data` Docker volume between restarts.

---

## 5. Verify it works

### Health check

```bash
curl -s http://localhost:8088/health | python3 -m json.tool
```

Expected:

```json
{
  "status": "ok",
  "has_openmetadata": true,
  "has_slack": true,
  "has_ai": true,
  "db_path": "runtime/incidents.db",
  "queue_depth": 0
}
```

`has_*` fields will be `false` if the corresponding credential is not set —
this is fine for a first run.

### Run the test suite

```bash
python3 -m pytest tests/ -q
```

All 245 tests should pass. This works without any credentials.

### Full verify script (tests + demo + determinism proof)

```bash
./scripts/verify.sh
```

This runs the test suite, fires a fixture-backed incident through the pipeline,
renders the 4-block brief in the terminal, and confirms that two runs produce
byte-identical output (md5 hash parity). Should take under 30 seconds.

### Fire a manual webhook

```bash
curl -s -X POST http://localhost:8088/webhooks/incidents \
  -H 'Content-Type: application/json' \
  -d '{
    "entity": {
      "id": "tc-manual-test",
      "fullyQualifiedName": "demo_mysql.customer_analytics.raw.customer_profiles",
      "testDefinition": {"name": "columnValueNullRatioExceeded"},
      "testCaseResult": {
        "testCaseStatus": "Failed",
        "result": "null ratio on customer_id exceeded 15% threshold (observed 0.23)"
      }
    }
  }' | python3 -m json.tool
```

Then open `http://localhost:8088/` — the incident row appears. Open
`http://localhost:8088/incidents/tc-manual-test-.../view` for the HTML report.

---

## 6. Connect OpenMetadata

### 6.1 — Run OpenMetadata locally

If you don't have an existing OM instance:

```bash
mkdir ~/om-local && cd ~/om-local
curl -sL -o docker-compose.yml \
  https://github.com/open-metadata/OpenMetadata/releases/download/1.12.0-release/docker-compose.yml
docker compose up -d
```

First boot takes ~2 minutes. UI will be at `http://localhost:8585`.
Default login: `admin@open-metadata.org` / `admin`.

> **Port conflict:** OpenMetadata's compose also starts Airflow on port 8080.
> If you're running the copilot locally (not in Docker), set `COPILOT_PORT=8088`
> in your `.env` to avoid the collision.

### 6.2 — Get a JWT token

1. Log in to OpenMetadata as admin.
2. **Settings** (gear icon, top right) → **Bots** (left sidebar).
3. Click **ingestion-bot**.
4. In the **JWT Token** row → set expiry to **Unlimited** → click **Revoke & Generate New Token**.
5. Copy the `eyJraWQi...` string.

Set in `.env`:

```bash
OPENMETADATA_BASE_URL=http://localhost:8585/api
OPENMETADATA_JWT_TOKEN=eyJraWQi...
```

Sanity-check:

```bash
curl -H "Authorization: Bearer $OPENMETADATA_JWT_TOKEN" \
  $OPENMETADATA_BASE_URL/v1/system/version
# Should return JSON with {"version": "1.12.x", ...}
```

### 6.3 — Wire OM alerts to the copilot (webhook path)

1. In OpenMetadata: **Settings → Notifications → Alerts → Create**.
2. Name it `Incident Copilot`.
3. **Source:** `Test Case` — trigger: **Test Case Status Change**.
4. **Filter:** `Test Case Status = Failed`.
5. **Destination:** `Webhook` → `Generic`.
6. **Endpoint URL:**
   - Copilot running locally (not in Docker): `http://localhost:8088/webhooks/incidents`
   - Copilot inside same Docker Compose network: `http://copilot:8080/webhooks/incidents`
   - Copilot accessible from OM's Docker: `http://host.docker.internal:8088/webhooks/incidents`
7. Save → click **Send Test** — a new row should appear on the copilot dashboard.

> **OM blocks private IPs by default.** In newer OM versions the alert UI refuses
> to save a private-IP endpoint. Work around by using ngrok even for the webhook:
> `ngrok http 8088` → use the `https://xxx.ngrok.io/webhooks/incidents` URL.

### 6.4 — Alternative: polling mode (no inbound firewall holes)

If OM can't reach the copilot, flip to polling instead:

```bash
COPILOT_ENABLE_POLLER=true
COPILOT_POLLER_INTERVAL_SECONDS=60
OPENMETADATA_BASE_URL=http://localhost:8585/api
OPENMETADATA_JWT_TOKEN=eyJraWQi...
```

The copilot polls OM every 60 seconds, deduplicates by `incident_id`, and runs
each new failure through the pipeline automatically. No OM-side config needed.

---

## 7. Connect Slack

### 7.1 — Create the Slack app

1. Go to `https://api.slack.com/apps` → **Create New App → From scratch**.
2. Name: `Incident Copilot`. Workspace: yours.

### 7.2 — Incoming Webhook (to post briefs)

3. Left sidebar → **Incoming Webhooks** → toggle On.
4. Scroll down → **Add New Webhook to Workspace** → pick your `#data-incidents` channel.
5. Copy the URL: `https://hooks.slack.com/services/T.../B.../...`

Set in `.env`:

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...
```

Test it:

```bash
curl -X POST $SLACK_WEBHOOK_URL \
  -H "Content-Type: application/json" \
  -d '{"text": "copilot alive"}'
```

### 7.3 — Interactive buttons (Acknowledge / Approve / Deny)

This requires a public URL for the copilot. For local development, use ngrok:

```bash
ngrok http 8088
# Copy the https URL, e.g. https://a1b2c3d4.ngrok.io
```

6. In your Slack app: **Interactivity & Shortcuts** → toggle On.
7. **Request URL:** `https://a1b2c3d4.ngrok.io/slack/actions`
8. **Save Changes.**
9. **Basic Information** → **App Credentials** → copy **Signing Secret**.

Set in `.env`:

```bash
SLACK_SIGNING_SECRET=abc123def456...
```

Restart the copilot. Now clicking Acknowledge / Approve / Deny in Slack:
- Verifies HMAC signature (replays and forgeries get 401)
- Writes `delivery_status = "acked_by:<user>"` to the SQLite audit log
- Posts an ephemeral private confirmation to the clicker via `chat.postEphemeral`

### 7.4 — Slash command (`/metadata search`)

Optional. Lets anyone in Slack type `/metadata search <query>` to search your
OpenMetadata catalog directly from Slack.

10. **Slash Commands → Create New Command.**
11. Command: `/metadata`. Request URL: `https://a1b2c3d4.ngrok.io/slack/commands`.
12. Save. Reinstall the app to your workspace if prompted.

### 7.5 — Daily digest

Post a daily incident summary to Slack on a schedule:

```bash
curl -X POST http://localhost:8088/slack/digest
```

Wire this to a cron job or your CI scheduler to run every morning.

---

## 8. Enable AI narratives (OpenRouter)

1. Sign up at `https://openrouter.ai`.
2. **Dashboard → Keys → Create Key**. Copy the `sk-or-v1-...` string.
3. Add $1–5 of credit (Haiku calls cost ~$0.0001 each).

Set in `.env`:

```bash
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=anthropic/claude-haiku-4-5    # default; omit to use default
```

Restart the copilot. The `has_ai: true` flag will appear in `/health`.

Without this key the service uses deterministic template strings for:
- RCA narratives ("Null ratio exceeded threshold — likely upstream null propagation.")
- "What to do next" bullets (static per policy state)
- Novel signal classification (falls back to "unknown / manual investigation")
- DQ test suggestions (rule-based heuristics instead of AI analysis)

**The pipeline works fully without the key.** It just uses less interesting text.

To switch models:

```bash
OPENROUTER_MODEL=anthropic/claude-opus-4-5     # more capable, more expensive
OPENROUTER_MODEL=anthropic/claude-haiku-4-5    # default, very fast, cheap
OPENROUTER_MODEL=openai/gpt-4o                 # non-Claude alternative
```

---

## 9. Run via Docker

### Build and run

```bash
# From projects/main-submission/
docker compose up --build
```

Service runs on `http://localhost:8080`.

Note: default `COPILOT_PORT` in the container is `8080`. Set that in `.env`:

```bash
COPILOT_PORT=8080
```

If you're also running OpenMetadata's compose (which starts Airflow on 8080),
the host port 8080 will conflict. Either:
- Change the host port in `compose.yml`: `"8088:8080"` (map host 8088 → container 8080)
- Or use Docker Compose network isolation and only talk to the copilot from inside the network

### Inspect a running container

```bash
docker exec -it incident-copilot sh
# Inside: curl localhost:8080/health
```

### Persistent storage

The `copilot-data` volume persists the SQLite DB across container restarts.
To wipe all incidents and start fresh:

```bash
docker compose down -v    # -v removes the volume
docker compose up -d
```

---

## 10. Endpoint reference

All endpoints return JSON unless noted.

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | HTML dashboard — recent incidents, integration status pills |
| `GET` | `/health` | Service health and integration flags |
| `GET` | `/metrics` | Incident counts and queue depth |
| `GET` | `/api` | JSON list of all endpoints |
| `POST` | `/webhooks/incidents` | Ingest an OpenMetadata alert (optional Bearer auth) |
| `GET` | `/incidents` | List all incidents (JSON, paginated) |
| `GET` | `/incidents/{id}` | Full canonical brief JSON for one incident |
| `GET` | `/incidents/{id}/view` | HTML one-page report for post-mortems |
| `GET` | `/rca-summary` | Aggregated RCA view bucketed by signal type |
| `GET` | `/admin/retry-queue` | Pending Slack delivery retries |
| `POST` | `/admin/retry-now` | Immediately flush the retry queue |
| `GET` | `/admin/dead-letter` | Items that exhausted all retry attempts |
| `DELETE` | `/admin/dead-letter/{id}` | Discard a dead-letter item |
| `POST` | `/slack/actions` | Slack interactivity endpoint (HMAC-verified) |
| `POST` | `/slack/commands` | Slack `/metadata search <query>` slash command |
| `POST` | `/slack/digest` | Post daily incident summary to Slack |

### MCP tools (for AI agent composition)

Start the MCP server:

```bash
python3 src/incident_copilot/mcp_facade.py
```

Available tools:

| Tool | What it does |
|---|---|
| `triage_incident(incident_id, entity_fqn)` | Run full pipeline, return canonical brief |
| `score_impact(entity_fqn, lineage_depth)` | Return scored impacted asset list |
| `get_rca(test_case_id, signal_type)` | Return cause tree + narrative |
| `notify_slack(incident_id, brief)` | Post brief to Slack, return payload hash |
| `suggest_tests_for_table(entity_fqn)` | Suggest DQ tests for a table's schema |
| `create_tests_in_om(entity_fqn, suggestions)` | Write suggested tests back to OM via REST |
| `list_recent_failures(limit)` | List recent incidents from the copilot's store |
| `get_table_info(entity_fqn)` | Fetch table owners, tags, columns from OM |

---

## 11. Troubleshooting

### Service won't start

```
ERROR: COPILOT_DB_PATH directory does not exist
```
Fix: `mkdir -p runtime`

```
ERROR: Port already in use
```
Fix: `lsof -ti:8088 | xargs kill` or change `COPILOT_PORT` in `.env`

### `has_openmetadata: false` in /health

- Check `OPENMETADATA_BASE_URL` is set and reachable: `curl $OPENMETADATA_BASE_URL/v1/system/version`
- Check `OPENMETADATA_JWT_TOKEN` is set and not expired
- If running OM in Docker and copilot outside: use `http://host.docker.internal:8585/api` not `localhost`

### `has_slack: false` in /health

- Check `SLACK_WEBHOOK_URL` is exported: `echo $SLACK_WEBHOOK_URL`
- Test it directly: `curl -X POST $SLACK_WEBHOOK_URL -d '{"text":"test"}'`
- Re-source your `.env`: `set -a && source .env && set +a`

### Slack buttons do nothing when clicked

- ngrok tunnel died — relaunch `ngrok http 8088`, update the Request URL in your Slack app's Interactivity settings
- `SLACK_SIGNING_SECRET` not set — the endpoint returns 401 for every button click

### Webhook lands but brief is empty / wrong

- Check the raw payload is hitting the endpoint: `tail -f /tmp/copilot.log`
- The parser accepts both the native OM webhook shape and the canonical envelope shape
- If `entity_fqn` can't be resolved in OM, the service falls back to fixture data and logs `OM_HTTP_FALLBACK_TO_FIXTURE` in `fallback_reason_codes` — this is intentional, not a crash

### `approval_required` never shows up

- The policy triggers only when a `PII.Sensitive`-tagged asset is in the downstream lineage
- Tag a column or table in OM with `PII.Sensitive` and ensure it appears as a lineage child of your test table

### Tests fail with `no such table`

- Caused by tests using `:memory:` SQLite with multiple connections. All tests use `tmp_path` file-based SQLite now — if you see this, it's a new test that needs the same treatment.

### Port 8080 conflict with OpenMetadata's Airflow

OpenMetadata's Docker Compose bundles Airflow on port 8080. Set `COPILOT_PORT=8088`
in `.env` and use `http://localhost:8088` everywhere.
