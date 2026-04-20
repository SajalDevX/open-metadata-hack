# Known Gaps & Follow-up Notes

Living document of things that are deliberately unfinished, known-broken, or deferred.
Updated as features land or issues are discovered.

## Deferred (out of scope for current phase)

- **Multi-incident correlation** — the base design explicitly excluded this. Would need a
  separate "incident bundle" concept and dedup beyond `incident_id`.
- **Google Workspace integration** — #26645 asks for creating Google Sheets / Docs from
  incident data. Out of scope: requires OAuth setup and GW MCP client that can't be
  built without credentials.
- **"Hey @metadata-bot" Slack mentions** — NL Q&A via Slack Events API needs an
  event subscription endpoint + persistent bot token. Omitted deliberately; the
  `/metadata search` slash command covers the discovery use-case.

## Known limitations

- **No authentication on the service.** Webhook endpoint supports optional bearer-token
  auth via `WEBHOOK_SECRET` env var. Deploy behind a VPN / private network for
  production without it.
- **Retry worker is best-effort.** Max retries capped, no exponential backoff jitter.
  Good enough for hackathon; production would add those.
- **Poller assumes OM REST endpoint exists** on the configured base URL.
  Failure to reach it logs and continues — no circuit breaker.
- **Pipeline runs inline on webhook.** A burst of alerts will queue on uvicorn's
  event loop. Fine for expected OM alert volume (< 1/s); would need a worker queue
  at higher rates.
- **HTML renderer is dark-theme only.** No light-mode toggle.

## Spotted during live OM testing (2026-04-19) — all fixed

- **`webhook_parser` drops `entity.testCaseResult.result`** — ✅ Fixed in `fix: preserve
  table-level FQN and thread failed_test message through webhook envelope to RCA`. The
  `failed_test` field is now threaded from the webhook envelope through to the RCA engine,
  overriding synthetic OM placeholders.
- **Port 8080 collision in local-dev OpenMetadata stack** — Airflow (bundled in OM's
  compose) binds 8080. The copilot default also was 8080. Moved copilot to
  `COPILOT_PORT=8088` in `.env`. Docker compose users are unaffected since they get
  their own network namespace.

## Things I'd like to revisit

- `score_impact` MCP tool currently creates a synthetic incident envelope; would be
  cleaner as a direct asset-query that doesn't fabricate an incident_id.

## Partial coverage of hackathon problem statements

### [#26659](https://github.com/open-metadata/OpenMetadata/issues/26659) — Human-readable RCA (~85% covered)

- **Aggregated RCA dashboard** — ✅ `GET /rca-summary` endpoint added. Buckets incidents
  by `signal_type` with count, approval_required count, and 5 most recent per bucket.
- **Novel signal classification** — ✅ When signal is `unknown` and AI is available,
  Claude now classifies the failure into a new cause tree instead of the generic bucket.
- **Remaining:** Instrumenting OM's test runners to emit richer diagnostic data is
  out of scope for a read-only consumer.

### [#26658](https://github.com/open-metadata/OpenMetadata/issues/26658) — DQ Checks Impact scoring (~85% covered)

- **Robustness under changing usage patterns** — scoring formula is stable by construction
  but no formal simulation benchmarks. Not a code gap.

### [#26660](https://github.com/open-metadata/OpenMetadata/issues/26660) — AI-Powered DQ Recommendations (~70% covered)

- **Proactive test suggestion** — ✅ `suggest_tests_for_table(entity_fqn)` MCP tool added.
  Fetches table columns from OM, generates rule-based DQ test suggestions (null, unique,
  regex for emails, between for numeric metrics) and Claude-powered suggestions when
  `OPENROUTER_API_KEY` is set.
- **Remaining:** Tool suggests tests but doesn't write them back to OM. Creating test
  cases via OM's REST API is a possible extension but not in scope.

### [#26645](https://github.com/open-metadata/OpenMetadata/issues/26645) — Multi-MCP Agent Orchestrator (~50% covered)

- **Google Workspace** and **cross-platform multi-step workflows** are out of scope
  (see Deferred section above). The OM → copilot → Slack workflow is demonstrated end-to-end.

### [#26609](https://github.com/open-metadata/OpenMetadata/issues/26609) — New MCP Tools (~60% covered)

- ✅ Alert/Notification tools: `notify_slack`, `triage_incident`
- ✅ Data Insights tools: `list_recent_failures`, `get_table_info`, `score_impact`
- ✅ DQ recommendation tools: `suggest_tests_for_table`
- **Remaining:** Workflow automation (trigger ingestion pipelines), Domain & Data Product
  management, and Import/Export tools.

### [#26651](https://github.com/open-metadata/OpenMetadata/issues/26651) — Slack App for OpenMetadata (~75% covered)

- ✅ `/metadata search <query>` slash command — `POST /slack/commands` endpoint routes
  Slack slash commands to OM's search API and returns Slack blocks with FQN/description/owner.
- ✅ Daily digest — `POST /slack/digest` endpoint posts a signal-type summary + recent
  incidents to the configured Slack webhook. Can be triggered on a schedule (cron / external).
- **Remaining:** "Hey @metadata-bot" @mention Q&A (requires Slack Events API subscription).

## Problem-statement coverage honesty score

| Issue | Title | Coverage | Change |
|---|---|---|---|
| #26659 | Human-readable RCA | ~85% | +15% (rca-summary, novel signal classification) |
| #26658 | DQ Impact scoring | ~85% | unchanged |
| #26660 | AI-Powered DQ Recommendations | ~70% | +40% (suggest_tests_for_table) |
| #26645 | Multi-MCP Agent Orchestrator | ~50% | unchanged (GW out of scope) |
| #26609 | New MCP Tools | ~60% | +3 new tools (list_recent_failures, get_table_info, suggest_tests) |
| #26651 | Slack App for OpenMetadata | ~75% | +35% (slash command + daily digest) |

Net: **6 of 22** hackathon problem statements touched, **5 substantially** covered
(#26659, #26658, #26660, #26609, #26651), **1 partially** covered (#26645).

## Completed items from deferred/gap list

| Item | Status |
|---|---|
| `OPENROUTER_MODEL` env var | ✅ Done |
| Non-root Dockerfile user | ✅ Done (uid 1001, `copilot`) |
| `GET /admin/dead-letter` DLQ viewer | ✅ Done (+ `DELETE /admin/dead-letter/{id}`) |
| `GET /rca-summary` aggregated dashboard | ✅ Done |
| Optional bearer-token auth on `/webhooks/incidents` | ✅ Done (`WEBHOOK_SECRET`) |
| `suggest_tests_for_table` MCP tool | ✅ Done |
| `POST /slack/commands` slash command | ✅ Done |
| `POST /slack/digest` daily digest | ✅ Done |
| `list_recent_failures` + `get_table_info` MCP tools | ✅ Done |
| RCA novel signal classification via Claude | ✅ Done |
| Update OPENMETADATA_ALERT_SETUP.md with real discoveries | ✅ Done |

## Verified working (as of latest commit)

- **238 tests pass**
- Live FastAPI service:
  - `GET  /` — HTML dashboard with recent incidents + integration-status pills
  - `POST /webhooks/incidents` — ingest OM alert payloads (optional `WEBHOOK_SECRET` auth)
  - `GET  /incidents` / `/incidents/{id}` / `/incidents/{id}/view`
  - `GET  /health` / `/metrics`
  - `GET  /rca-summary` — aggregated RCA view bucketed by signal_type
  - `GET  /admin/retry-queue` / `POST /admin/retry-now`
  - `GET  /admin/dead-letter` / `DELETE /admin/dead-letter/{id}`
  - `POST /slack/actions` — signed Slack interactivity (ack/approve/deny)
  - `POST /slack/commands` — Slack `/metadata search <query>` slash command
  - `POST /slack/digest` — post daily incident summary to Slack
  - `GET  /api` — endpoint listing JSON
- MCP tools: `triage_incident`, `score_impact`, `get_rca`, `notify_slack`,
  `suggest_tests_for_table`, `list_recent_failures`, `get_table_info`
- SQLite persistence + retry queue + dead-letter queue
- Background retry loop + OM event poller, managed by FastAPI lifespan
- Slack Block Kit message with ack/approve/deny buttons; `/slack/actions` verifies HMAC
- Dockerfile runs as non-root user (uid 1001, `copilot`)
- `OPENROUTER_MODEL` env var controls which Claude model is used
- `WEBHOOK_SECRET` env var enables bearer-token auth on the ingest endpoint
- `verify.sh` proves determinism (md5 parity across runs)
