# Known Gaps & Follow-up Notes

Living document of things that are deliberately unfinished, known-broken, or deferred.
Updated as features land or issues are discovered.

## Deferred (out of scope for current phase)

- **Slack interactive buttons** (ack/approve/deny) — Phase C. Currently one-way delivery.
- **Docker / docker-compose packaging** — Phase C.
- **Multi-incident correlation** — the base design explicitly excluded this. Would need a
  separate "incident bundle" concept and dedup beyond `incident_id`.
- **Web UI for browsing incident history** — only `/incidents/{id}/view` HTML exists;
  no index/dashboard page yet.
- **OpenMetadata alert-configuration guide** — need step-by-step doc for pointing OM
  Settings → Alerts at the copilot webhook.

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

## Things I'd like to revisit

- `score_impact` MCP tool currently creates a synthetic incident envelope; would be
  cleaner as a direct asset-query that doesn't fabricate an incident_id.
- RCA cause tree is a flat 5-signal lookup — could be extended with an `other` bucket
  that uses Claude to classify novel signals into new cause tree nodes.
- OpenRouter model is hardcoded to `anthropic/claude-haiku-4-5`; should be an env var.

## Verified working (as of latest commit)

- 140+ tests pass
- Live FastAPI service: `/webhooks/incidents`, `/incidents`, `/health`, `/metrics`
- SQLite persistence with upsert-by-id
- One-click `verify.sh` proves determinism (md5 parity across runs)
- Real Slack webhook delivery (urllib POST)
- Real OpenMetadata HTTP + MCP transport clients
- Real OpenRouter Claude calls with template fallback
