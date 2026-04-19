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

## Verified working (as of latest commit)

- **179 tests pass**
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
