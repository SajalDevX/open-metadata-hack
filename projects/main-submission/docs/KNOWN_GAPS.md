# Known Gaps & Follow-up Notes

Living document of things that are deliberately unfinished, known-broken, or deferred.
Updated as features land or issues are discovered.

## Deferred (out of scope for current phase)

- **Multi-incident correlation** — the base design explicitly excluded this. Would need a
  separate "incident bundle" concept and dedup beyond `incident_id`.
- **Authenticated webhook endpoint** — no HMAC / bearer-token check on
  `/webhooks/incidents`. Deliberate: OM's outbound webhook auth story varies
  per version. Deploy behind a private network or reverse proxy with
  basic auth for production.
- **Non-root container user** — Dockerfile runs as default python user. Fine for
  hackathon; production image should build a dedicated UID.
- **Retry-queue dead-letter storage** — after `max_attempts` the entry is
  filtered out but left in the DB. A real DLQ viewer endpoint would help ops.

## Known limitations

- **No authentication on the service.** Webhook endpoint is open — fine for a private
  deployment behind a VPN / trusted network, not for public internet.
- **Retry worker is best-effort.** Max retries capped, no exponential backoff jitter,
  no dead-letter queue. Good enough for hackathon; production would add those.
- **Poller assumes OM REST `/events` endpoint exists** on the configured base URL.
  Failure to reach it logs and continues — no circuit breaker.
- **Pipeline runs inline on webhook.** A burst of alerts will queue on uvicorn's
  event loop. Fine for expected OM alert volume (< 1/s); would need a worker queue
  at higher rates.
- **HTML renderer is dark-theme only.** No light-mode toggle.

## Spotted during live OM testing (2026-04-19)

- **`webhook_parser` drops `entity.testCaseResult.result`** — OM's alert payload
  includes the failed-test message directly, but the parser only extracts
  `{incident_id, entity_fqn, test_case_id, severity, occurred_at, raw_ref}` and
  lets the Context Resolver re-query OM for the full test case. When the
  test_case_id doesn't exist in OM (e.g. we wrote it ad-hoc), we fall back
  to empty `failed_test` → signal_type="unknown" → generic RCA narrative.
  Fix: thread the `testCaseResult.result` into the envelope as a `failed_test`
  hint, consumed by Context Resolver when OM lookup fails.
- **Port 8080 collision in local-dev OpenMetadata stack** — Airflow (bundled in
  OM's compose) binds 8080. The copilot default also was 8080. Moved copilot
  to `COPILOT_PORT=8088` in `.env`. Docker compose users are unaffected since
  they get their own network namespace.

## Things I'd like to revisit

- `score_impact` MCP tool currently creates a synthetic incident envelope; would be
  cleaner as a direct asset-query that doesn't fabricate an incident_id.
- RCA cause tree is a flat 5-signal lookup — could be extended with an `other` bucket
  that uses Claude to classify novel signals into new cause tree nodes.
- OpenRouter model is hardcoded to `anthropic/claude-haiku-4-5`; should be an env var.

## Partial coverage of hackathon problem statements

Each of the six problem statements the project targets is partially — not
fully — addressed. Documenting the specific unaddressed sub-items per issue so
a reader can see exactly what would complete each one.

### [#26659](https://github.com/open-metadata/OpenMetadata/issues/26659) — Human-readable RCA (~70% covered)

- **Aggregated RCA dashboard** — no cross-incident view grouping by `signal_type`
  or cause tree node. Dashboard at `/` is a flat incident list. Would need a
  `/rca-summary` endpoint that buckets incidents by `rca.signal_type` with counts.
- **Instrument existing checks to emit provenance and diagnostic signals** —
  we consume OM's test result message as-is. The issue asks for instrumenting
  OM's test runners themselves to emit richer diagnostic data. Out of scope
  for a read-only consumer.

### [#26658](https://github.com/open-metadata/OpenMetadata/issues/26658) — DQ Checks Impact scoring (~85% covered)

- **Robustness under changing usage patterns** — judging criterion we never
  formally benchmarked. Scoring formula is stable by construction
  (`downstream_count` is the only dynamic term via `log₂`) but we didn't run
  simulations showing how scores drift under traffic bursts, lineage depth
  changes, etc.

### [#26660](https://github.com/open-metadata/OpenMetadata/issues/26660) — AI-Powered DQ Recommendations (~30% covered — biggest gap)

- **Proactive test suggestion** is the core ask: analyze a table's profile
  and suggest which DQ tests to *add*. Our `ai_recommender.py` is reactive —
  it suggests what to do *about* a failed test. Different axis entirely.
- **Reading column types, names, descriptions, sample data** — we don't query
  the OpenMetadata profile endpoint at all.
- **Suggesting test definitions from the template library** — no integration
  with OpenMetadata's built-in test templates.
- **Creating test cases with default parameters** — we don't write to OM.
- *Fix path:* add a new `suggest_tests_for_table(entity_fqn)` MCP tool that
  pulls the table's profile + column metadata from OM, prompts Claude for a
  list of relevant test definitions with parameters, and returns a JSON list.
  Estimated effort: < 1 hour.

### [#26645](https://github.com/open-metadata/OpenMetadata/issues/26645) — Multi-MCP Agent Orchestrator (~50% covered)

- **Google Workspace integration** — issue's examples involve creating Google
  Sheets, Google Docs. We only do Slack. Would need a Google Workspace MCP
  client + scope / auth setup.
- **Cross-platform workflows demonstration** — we compose OM → copilot → Slack,
  but we haven't demonstrated a multi-step agent workflow like
  "find DQ failures → create Google Sheet summary → post to Slack channel".

### [#26609](https://github.com/open-metadata/OpenMetadata/issues/26609) — New MCP Tools (1-of-5 sub-options covered)

- The issue offered five independent sub-options; we shipped the Alert/Notification
  one via `notify_slack`. Other four sub-options we didn't build:
  - Data Insights / KPI tools
  - Workflow automation tools (trigger/monitor ingestion pipelines)
  - Domain & Data Product management
  - Import/Export tools

### [#26651](https://github.com/open-metadata/OpenMetadata/issues/26651) — Slack App for OpenMetadata (~40% covered)

- **`/metadata search` slash command** — no Slack slash command registered.
  Would need to register one in the Slack app config and route it to a new
  `POST /slack/commands` endpoint that queries OpenMetadata's search API.
- **Daily digest** — no scheduled job that posts a daily summary of metadata
  changes, quality status, or pending governance to a channel.
- **"Hey @metadata-bot, who owns the payments table?"** — no event-listener
  for mentions + natural language Q&A. Would need Slack Events API subscription
  and a Claude-backed Q&A flow.

## Problem-statement coverage honesty score

| Issue | Title | Coverage |
|---|---|---|
| #26659 | Human-readable RCA | ~70% |
| #26658 | DQ Impact scoring | ~85% |
| #26660 | AI-Powered DQ Recommendations | ~30% |
| #26645 | Multi-MCP Agent Orchestrator | ~50% |
| #26609 | New MCP Alert/Notification Tools | 100% of this slice, 0% of other slices |
| #26651 | Slack App for OpenMetadata | ~40% |

Net: **6 of 22** hackathon problem statements touched, **3 substantially** covered
(#26659, #26658, #26609), **3 partially** covered (#26660, #26645, #26651),
**0 fully** covered end-to-end. This is deliberate — we prioritised depth and
integration coherence in one coherent product over breadth across unrelated
half-demos.

## Verified working (as of latest commit)

- **190 tests pass**
- Live FastAPI service:
  - `GET  /` — HTML dashboard with recent incidents + integration-status pills
  - `POST /webhooks/incidents` — ingest OM alert payloads
  - `GET  /incidents` / `/incidents/{id}` / `/incidents/{id}/view`
  - `GET  /health` / `/metrics`
  - `GET  /admin/retry-queue` / `POST /admin/retry-now`
  - `POST /slack/actions` — signed Slack interactivity (ack/approve/deny)
  - `GET  /api` — endpoint listing JSON
- SQLite persistence (`store.py`) + retry queue (`delivery_queue.py`)
- Background retry loop + OM event poller, managed by FastAPI lifespan
- Startup config validator — warns on missing optional integrations, errors on
  partial OpenMetadata config or invalid port
- Slack Block Kit message with ack/approve/deny buttons; `/slack/actions`
  verifies HMAC signatures and rejects replays > 5 min old
- Dockerfile + docker-compose.yml — `docker compose up` spins up the service
- `.env.example` documents every supported env var
- `docs/OPENMETADATA_ALERT_SETUP.md` step-by-step for pointing OM at the webhook
- One-click `verify.sh` proves determinism (md5 parity across runs)
- Real Slack webhook delivery (urllib POST) with Block Kit payload
- Real OpenMetadata HTTP + MCP transport clients
- Real OpenRouter Claude calls with template fallback
- Verified in-container end-to-end: health, webhook ingest, dashboard all served
