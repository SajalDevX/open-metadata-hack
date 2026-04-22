# Task Plan

- [x] Add tests for Slack sender webhook success, failure, and not-configured fallback.
- [x] Add facade test coverage for env-driven Slack send attempts and deterministic payload hashing.
- [x] Implement the minimal stdlib webhook sender and wire `notify_slack_tool` to use it.
- [x] Run targeted pytest, then the full suite, and fix any regressions.
- [x] Record verification notes and commit the green change.

## Review

- Slack delivery now attempts a real webhook POST when `SLACK_WEBHOOK_URL` or `SLACK_WEBHOOK` is set, and still returns `not_configured` with `fallback=local_mirror` when no webhook is present.
- Canonical payload hashing remains stable because the facade still hashes the sorted JSON brief.
- Verification: `.venv/bin/python -m pytest -q tests/test_mcp_facade.py tests/test_slack_sender.py` and `.venv/bin/python -m pytest -q`.

## Task C/D Review Fixes

- [x] Add structuredContent-first parsing in the MCP transport client while keeping legacy content-shape compatibility.
- [x] Cover MCP transport HTTPError and URLError branches with direct tests.
- [x] Exercise resolver fallback through `MCPTransportClientError` on the real client path.
- [x] Make Slack sender reject malformed/non-dict `brief` payloads without crashing.
- [x] Isolate the notify hash test from ambient Slack webhook env vars.
- [x] Verify the focused task suite and the full pytest run.

## OpenMetadata Live Integration Resume (2026-04-19)

- [x] Re-validate local OpenMetadata service health and auth.
- [x] Re-run seeded live replay against `OPENMETADATA_BASE_URL=http://localhost:8585/api`.
- [x] Re-run original replay fixture against live OpenMetadata.
- [x] Reconfirm fallback reason codes for both paths via direct `run_pipeline` checks.
- [x] Run graph-backed hotspot analysis for OpenMetadata integration flow.
- [x] Capture concrete "working vs not working" state and prioritized testing gaps.

## OpenMetadata Resume Review

- Seeded live replay remains healthy: owner routing resolves from live OpenMetadata (`admin via asset_owner`) and fallback reasons only include Slack delivery degradation (`SLACK_SEND_FAILED`).
- Original replay fixture still falls back to fixture context with degraded owner routing:
  `MISSING_OWNER_METADATA`, `OM_HTTP_FALLBACK_TO_FIXTURE`, `SLACK_SEND_FAILED`.
- Root issue remains fixture/live FQN mismatch (`customer_analytics.raw.customer_profiles` style fixture vs service-prefixed OpenMetadata FQN hierarchy).
- Graph + focused review highlight testing risk concentration in OpenMetadata paths, especially incomplete branch coverage for combined fallback chains and thin OpenMetadata client coverage.

## OpenMetadata Integration Hardening Plan (Current Pass)

- [x] Add tests for full fallback-chain reason code behavior (`MCP -> HTTP -> fixture`).
- [x] Add tests for OpenMetadata FQN mapping attempts from fixture-style 3-part FQNs.
- [x] Implement minimal FQN mapping strategy in OpenMetadata HTTP client.
- [x] Run targeted pytest for resolver/client/demo harness tests.
- [x] Re-run live replay checks (seeded + original fixture) and update validation notes.

## OpenMetadata Hardening Review (Current Pass)

- Added resolver fallback-chain coverage and OpenMetadata FQN mapping coverage first (red), then implemented minimal mapping in client (green).
- Full suite is green after changes: `.venv/bin/python -m pytest -q` -> `87 passed`.
- Live validation with `OPENMETADATA_FQN_SERVICE_HINTS=demo_mysql` now resolves both seeded and original replay events via live OpenMetadata owner metadata.
- Original replay fixture no longer emits `OM_HTTP_FALLBACK_TO_FIXTURE` in the validated environment; fallback reasons now only include Slack send degradation (`SLACK_SEND_FAILED`) because Slack is intentionally unconfigured.

## OpenMetadata One-Shot Validation Script

- [x] Add reusable helper module for live-context degradation assertions and replay FQN candidate expansion.
- [x] Add one-shot script: seed-check (`table exists`) + replay + assert no OpenMetadata-context degradation.
- [x] Run the script against `runtime/fixtures/replay_event.json` and store machine-readable report.
- [x] Re-run full pytest to ensure no regressions.

## One-Shot Script Review

- New script: `scripts/validate_live_openmetadata.py`
- New helper module: `src/incident_copilot/live_validation.py`
- New tests: `tests/test_live_validation.py`
- Script run result:
  - `status = ok`
  - `seeded_entity_fqn = demo_mysql.customer_analytics.raw.customer_profiles`
  - `who_acts_first = admin via asset_owner`
  - `fallback_reason_codes = ['SLACK_SEND_FAILED']`
  - report: `runtime/local_mirror/live_om_validation_report.json`
- Regression check:
  - `.venv/bin/python -m pytest -q` -> `92 passed`

## Create-If-Missing Bootstrap Extension

- [x] Extend one-shot validator from seed-check to seed-create-if-missing for service/database/schema/table hierarchy.
- [x] Run bootstrap path against a new replay entity to force creation.
- [x] Validate generated report includes `created_actions`.
- [x] Re-run full test suite after bootstrap changes.

## Bootstrap Extension Review

- `scripts/validate_live_openmetadata.py` now supports creation flow when replay candidates do not exist.
- Live creation-path smoke used:
  - `runtime/fixtures/replay_event_bootstrap_create.json`
  - created table: `demo_mysql.customer_analytics.raw.customer_profiles_bootstrap`
- Creation-path report confirms action tracking:
  - `runtime/local_mirror/live_om_validation_report.bootstrap-create.json`
  - `created_actions = ['created_table:demo_mysql.customer_analytics.raw.customer_profiles_bootstrap']`
- Full suite after changes:
  - `.venv/bin/python -m pytest -q` -> `95 passed`

## Security + Verification Hardening (2026-04-20)

- [x] Add webhook request authentication for `/webhooks/incidents` (HMAC secret) and reject unauthenticated calls.
- [x] Remove public canonical-envelope passthrough from webhook parser path and enforce strict event shape checks.
- [x] Enforce approver authorization on Slack actions for `approval_required` incidents.
- [x] Protect admin/read endpoints with API key gate and safe defaults for local demo.
- [x] Fix repo-root README command/doc paths so copy-paste works from root.
- [x] Add test dependency group and CI workflow for clean-environment verification.
- [x] Add one black-box service e2e test (real app request path, real artifact assertions).
- [x] Run focused and full verification (`pytest` + `scripts/verify.sh`) and record outcomes.

## Security + Verification Hardening Review (2026-04-20)

- Security hardening now enforces signed webhook ingestion (`X-Webhook-Timestamp` + `X-Webhook-Signature`) and rejects direct canonical incident envelopes on the public webhook route.
- Slack approval/deny actions for `approval_required` incidents now require user authorization via `COPILOT_APPROVER_USERS`; unauthorized users receive 403.
- Slack approver authorization now accepts stable Slack user IDs only (not mutable usernames).
- Read/admin endpoints now support API-key gating via `COPILOT_API_KEY`; admin routes require it, and read routes enforce it when configured (`/`, `/api`, `/metrics`, `/incidents*`).
- Added CI workflow at `.github/workflows/ci.yml` and test dependency extra (`.[test]`) in `pyproject.toml`.
- Added black-box e2e test `tests/test_service_e2e.py` covering signed webhook -> persisted brief -> protected read flow.
- Root README command/link paths now point to `projects/main-submission/...` surfaces for repo-root copy-paste correctness.
- Integration docs updated for webhook-signing requirements, API-key behavior, and Slack approver allowlist semantics.
- Verification:
  - `.venv/bin/python -m pytest -q` -> `199 passed`
  - `bash scripts/verify.sh` -> all checks passed (suite + demo + determinism + smoke + MCP)
