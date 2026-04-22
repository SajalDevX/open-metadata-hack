# Testing the Incident Copilot

Multiple ways to exercise the product, ordered from fastest to most thorough.

All commands assume you're inside `projects/main-submission/`.

---

## 1. Unit test suite (fastest, ~2 seconds)

```bash
python3 -m pytest tests/ -v
```

Expected: test suite passes with no failures.

---

## 2. One-shot verification script

Runs the full suite, demo pipeline, md5 determinism check, Python smoke test,
and MCP tool sanity check — all in one command.

```bash
./scripts/verify.sh
```

---

## 3. Run the live service locally

```bash
python3 scripts/run_server.py
```

In another terminal:

```bash
export COPILOT_WEBHOOK_SECRET=om-local-secret
export COPILOT_API_KEY=local-api-key

# Health check
curl http://localhost:8080/health | python3 -m json.tool

# Send a sample OpenMetadata alert
payload='{
  "entity": {
    "id": "tc-live-1",
    "fullyQualifiedName": "customer_analytics.raw.customer_profiles",
    "testCaseResult": {
      "testCaseStatus": "Failed",
      "result": "null ratio exceeded 15% threshold"
    }
  }
}'
ts=$(date +%s)
sig="v1=$(printf "v1:%s:%s" "$ts" "$payload" | openssl dgst -sha256 -hmac "$COPILOT_WEBHOOK_SECRET" -hex | sed 's/^.* //')"
curl -X POST http://localhost:8080/webhooks/incidents \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Timestamp: $ts" \
  -H "X-Webhook-Signature: $sig" \
  -d "$payload"

# List briefs
curl -H "X-API-Key: $COPILOT_API_KEY" http://localhost:8080/incidents | python3 -m json.tool

# Render dashboard HTML with API key
curl -H "X-API-Key: $COPILOT_API_KEY" http://localhost:8080/ > /tmp/dashboard.html

# See one brief rendered as HTML (use id from previous call)
curl -H "X-API-Key: $COPILOT_API_KEY" http://localhost:8080/incidents/<incident_id>/view > /tmp/brief.html

# Check metrics
curl -H "X-API-Key: $COPILOT_API_KEY" http://localhost:8080/metrics

# Inspect the retry queue
curl -H "X-API-Key: $COPILOT_API_KEY" http://localhost:8080/admin/retry-queue
```

---

## 4. Run it in Docker (production path)

```bash
cp .env.example .env        # edit or leave blank
docker compose up --build
```

Then hit the same endpoints at `http://localhost:8080`.

To stop:
```bash
docker compose down
```

To also wipe the persisted SQLite DB:
```bash
docker compose down -v
```

---

## 5. Full end-to-end with real integrations

```bash
cat > .env <<'EOF'
OPENMETADATA_BASE_URL=http://your-om-host:8585/api
OPENMETADATA_JWT_TOKEN=<ingestion-bot-token>
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...
SLACK_SIGNING_SECRET=<from Slack app config>
OPENROUTER_API_KEY=sk-or-...
EOF

docker compose up --build
```

Then in OpenMetadata go to **Settings → Alerts** and create a destination
pointing at `http://<copilot-host>:8080/webhooks/incidents`
(full guide in `docs/OPENMETADATA_ALERT_SETUP.md`).

Trigger any DQ check failure and watch:

- Dashboard at `/` shows the new row
- Slack channel gets a Block Kit message with 3 buttons
- Clicking a button hits `/slack/actions` and updates the brief status
- If you set `OPENROUTER_API_KEY`, the RCA narrative and "what to do next"
  bullets come from Claude via OpenRouter

---

## 6. Test specific features in isolation

```bash
# Only the live service endpoints
python3 -m pytest tests/test_app.py tests/test_app_retry.py -v

# Only the Slack interactivity (HMAC verification, replay protection, actions)
python3 -m pytest tests/test_slack_actions.py -v

# Only the OM poller
python3 -m pytest tests/test_om_poller.py -v

# Only the dashboard renderer
python3 -m pytest tests/test_dashboard.py -v

# Only the core pipeline components
python3 -m pytest tests/test_rca_engine.py tests/test_impact_scorer.py \
  tests/test_ai_recommender.py tests/test_policy.py -v

# Only the retry queue + background worker
python3 -m pytest tests/test_delivery_queue.py tests/test_background_retry.py -v
```

---

## 7. Test the MCP server path

```bash
python3 src/incident_copilot/mcp_facade.py
```

Starts a FastMCP server. Connect Claude Desktop / `mcp-cli` to it and call:

- `triage_incident(incident_id, entity_fqn)` — full pipeline → 4-block brief
- `score_impact(entity_fqn, lineage_depth)` — ranked scored assets
- `get_rca(test_case_id, signal_type)` — cause tree + narrative
- `notify_slack(incident_id, brief)` — post to Slack + return payload hash

---

## 8. Fast judge-demo sequence (30 seconds)

```bash
# Terminal 1
./scripts/verify.sh         # shows test + deterministic demo

# Terminal 2 (in another window)
export COPILOT_WEBHOOK_SECRET=om-demo-secret
export COPILOT_API_KEY=demo-api-key
python3 scripts/run_server.py

# Terminal 3
payload='{"entity":{"id":"tc-demo","fullyQualifiedName":"a.b.c","testCaseResult":{"testCaseStatus":"Failed","result":"null ratio"}}}'
ts=$(date +%s)
sig="v1=$(printf "v1:%s:%s" "$ts" "$payload" | openssl dgst -sha256 -hmac "$COPILOT_WEBHOOK_SECRET" -hex | sed 's/^.* //')"
curl -X POST http://localhost:8080/webhooks/incidents \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Timestamp: $ts" \
  -H "X-Webhook-Signature: $sig" \
  -d "$payload"

# Inspect protected reads
curl -H "X-API-Key: $COPILOT_API_KEY" http://localhost:8080/incidents | python3 -m json.tool
```

Proves: tests pass · deterministic output · live webhook ingestion · persistent
storage · HTML dashboard.

---

## What each test file covers

| File | Covers |
|---|---|
| `test_adapter.py` | Event normalization, missing-field fallback codes |
| `test_ai_recommender.py` | Claude bullets + policy fallback behavior |
| `test_app.py` | Webhook ingestion, CRUD endpoints, HTML view |
| `test_app_retry.py` | Retry enqueue on Slack failure, `/admin/retry-now` |
| `test_background_retry.py` | Retry worker success / failure / missing-brief paths |
| `test_brief.py` | Canonical 4-block brief generator |
| `test_brief_renderer.py` | HTML brief output, evidence tags, XSS escaping |
| `test_config.py` | Env-var → `AppConfig` mapping |
| `test_context_resolver.py` | MCP → HTTP → fixture fallback chain |
| `test_contracts.py` | Dataclass contracts for brief blocks, policy, scoring |
| `test_dashboard.py` | Dashboard index HTML, integration status pills |
| `test_delivery.py` | Slack vs local mirror parity, degraded modes |
| `test_delivery_queue.py` | Retry queue upsert, backoff, max-attempts |
| `test_demo_harness.py` | Deterministic replay |
| `test_impact.py` | Business-facing-first prioritization, depth bounds |
| `test_impact_scorer.py` | Deterministic scoring formula + `score_reason` |
| `test_live_validation.py` | Live OM bootstrap validation path |
| `test_mcp_facade.py` | MCP tool wrappers |
| `test_mcp_transport_client.py` | OM MCP JSON-RPC transport |
| `test_om_poller.py` | Poll OM for failed test results, cursor advance |
| `test_openmetadata_client.py` | Direct OM REST API client |
| `test_openrouter_client.py` | OpenAI-SDK → OpenRouter factory |
| `test_orchestrator.py` | End-to-end pipeline wiring |
| `test_owner_routing.py` | Asset → domain → team → default channel fallback |
| `test_policy.py` | `PII.Sensitive → approval_required` rule |
| `test_rca_engine.py` | Signal inference + Claude narrative + template fallback |
| `test_slack_actions.py` | Signed Slack interactivity, ack/approve/deny |
| `test_slack_sender.py` | Webhook POST + Block Kit payload generation |
| `test_startup_validator.py` | Config sanity check (warns/errors) |
| `test_store.py` | SQLite incident upsert, list, fetch |
| `test_terminal_renderer.py` | ANSI terminal brief output |
| `test_webhook_parser.py` | OM alert payload → canonical envelope |
| `test_validate_live_openmetadata.py` | Live OM reachability smoke |
