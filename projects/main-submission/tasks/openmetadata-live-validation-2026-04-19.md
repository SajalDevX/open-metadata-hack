# OpenMetadata Live Validation Notes (2026-04-19)

## Goal
Validate real OpenMetadata integration (no fixture fallback) and capture gaps.

## Environment Snapshot
- OpenMetadata API: `http://localhost:8585/api`
- Auth: `admin@open-metadata.org` login endpoint works, JWT token retrieval works.
- Slack intentionally not configured for this pass.

## What Was Seeded in OpenMetadata
- Database service: `demo_mysql`
- Database: `demo_mysql.customer_analytics`
- Database schema: `demo_mysql.customer_analytics.raw`
- Table: `demo_mysql.customer_analytics.raw.customer_profiles`

## Validation Runs

### A) Seeded live event (success path)
- Replay file: `runtime/fixtures/live_event_openmetadata.json`
- Output file: `runtime/local_mirror/live_om_seeded_brief.json`
- Result:
  - `fallback_reason_codes = ['SLACK_SEND_FAILED']`
  - `who_acts_first = admin via asset_owner`
  - No OpenMetadata HTTP fallback was triggered.

### B) Original replay fixture event (still fallback)
- Replay file: `runtime/fixtures/replay_event.json`
- Result:
  - `fallback_reason_codes = ['MISSING_OWNER_METADATA', 'OM_HTTP_FALLBACK_TO_FIXTURE', 'SLACK_SEND_FAILED']`
- Root cause:
  - Fixture entity FQN `customer_analytics.raw.customer_profiles` does not match seeded OpenMetadata FQN shape (`service.database.schema.table`).
  - Fresh OpenMetadata instance had empty catalog initially; fixture references unresolved entities/test cases.

## What Is Working
- OpenMetadata server connectivity and auth.
- Live HTTP context resolution path (`OM_CONTEXT_SOURCE=direct_http`) with JWT.
- End-to-end pipeline execution against real OM metadata.
- Owner routing from live OM owner metadata (`asset_owner` resolved to `admin`).

## What Is Not Working Yet
- Original replay fixture does not align with OpenMetadata FQN hierarchy and still falls back.
- No lineage edges for seeded table, so impacted set is empty (`what_is_impacted = none`).
- Test case creation attempt with generic definition failed (definition-specific parameters required).
- MCP transport live endpoint (`OPENMETADATA_MCP_URL`) not validated in this run.

## Recommended Next Improvements
1. Add a fixture-to-live FQN mapping layer (support 3-part fixture FQNs -> 4-part OM FQNs).
2. Seed/create lineage downstream nodes to validate impact scoring on non-empty lineage.
3. Create a concrete test case using a definition + required parameter values.
4. Add one integration script that:
   - seeds minimal OM entities,
   - runs live replay,
   - asserts no `OM_HTTP_FALLBACK_TO_FIXTURE` for mapped entities.
5. Validate MCP transport path separately once OM MCP endpoint/auth configuration is ready.

---

## Resume Pass (2026-04-19)

### Runtime Re-check
- Docker containers confirmed up:
  - `openmetadata_server` (healthy)
  - `openmetadata_mysql` (healthy)
  - `openmetadata_elasticsearch` (healthy)
- OpenMetadata version endpoint confirmed live:
  - `GET /api/v1/system/version -> 200` (`1.12.5`)
- Login endpoint confirmed live and JWT retrieval succeeded.

### Live Replay Re-run Outcomes

#### Seeded live replay (still healthy)
- Replay: `runtime/fixtures/live_event_openmetadata.json`
- Mirror: `runtime/local_mirror/live_om_seeded_brief.resume.json`
- Direct pipeline check:
  - `who_acts_first = admin via asset_owner`
  - `fallback_reason_codes = ['SLACK_SEND_FAILED']`

#### Original replay fixture (still degraded)
- Replay: `runtime/fixtures/replay_event.json`
- Mirror: `runtime/local_mirror/live_om_replay_brief.resume.json`
- Direct pipeline check:
  - `who_acts_first = #metadata-incidents via default_channel`
  - `fallback_reason_codes = ['MISSING_OWNER_METADATA', 'OM_HTTP_FALLBACK_TO_FIXTURE', 'SLACK_SEND_FAILED']`

### Graph + Review Risk Notes
- Flow criticality remains high for demo/replay path (`run_replay_command` criticality ~0.7072) and traverses `resolve_context` in the core path.
- Highest-risk test gaps to prioritize next:
  1. Combined fallback chain assertion (`MCP -> HTTP -> fixture`) with ordered reason codes.
  2. OpenMetadata client branch/error coverage beyond the single happy-path shape test.
  3. Replay harness assertions that pin sender side effects and payload persistence behavior.
  4. Owner fallback semantics for `domain_owner` / `team_owner` (not only `asset_owner`).
  5. Lineage depth/filter behavior for multi-hop and non-table nodes.

### Current Working / Not Working Snapshot

#### Working
- Local OpenMetadata service + auth integration.
- Live context resolution for seeded entity through direct HTTP path.
- Deterministic local mirror brief generation in replay runs.

#### Not Working Yet
- Original fixture path is not aligned with live OpenMetadata FQN model and still degrades.
- Impact remains trivial (`what_is_impacted = none`) for seeded scenario due missing richer lineage graph.
- Slack delivery is intentionally unconfigured in this validation scope.

---

## Hardening Pass Results (2026-04-19)

### Code/Test Changes Applied
- Added test coverage:
  - Resolver fallback chain ordering when both MCP and HTTP fail.
  - OpenMetadata fixture-FQN mapping behavior for 3-part -> service-prefixed FQN.
- Implemented minimal OpenMetadata client mapping strategy:
  - For 3-part entity FQNs, client now also tries service-prefixed candidates derived from:
    - `OPENMETADATA_FQN_SERVICE_HINTS` (comma-separated), or
    - `OPENMETADATA_SERVICE_NAME`.

### Verification
- Targeted tests:
  - `tests/test_context_resolver.py`
  - `tests/test_openmetadata_client.py`
  - `tests/test_demo_harness.py`
  - `tests/test_orchestrator.py`
  - `tests/test_mcp_transport_client.py`
- Full suite:
  - `.venv/bin/python -m pytest -q` -> `87 passed`

### Live Replay Validation (post-fix)
- Env used:
  - `OM_CONTEXT_SOURCE=direct_http`
  - `OPENMETADATA_BASE_URL=http://localhost:8585/api`
  - `OPENMETADATA_FQN_SERVICE_HINTS=demo_mysql`

#### Seeded replay
- Result:
  - `who_acts_first = admin via asset_owner`
  - `fallback_reason_codes = ['SLACK_SEND_FAILED']`

#### Original replay fixture
- Result:
  - `who_acts_first = admin via asset_owner`
  - `fallback_reason_codes = ['SLACK_SEND_FAILED']`
- Outcome change:
  - `OM_HTTP_FALLBACK_TO_FIXTURE` and `MISSING_OWNER_METADATA` are no longer present for this fixture in the validated environment.

---

## One-Shot Validation Automation (2026-04-19)

### Added
- Script: `scripts/validate_live_openmetadata.py`
  - Logs in to OpenMetadata.
  - Expands replay entity FQN to candidate forms using service hints.
  - Verifies seed presence by checking candidate table existence.
  - Runs replay via pipeline in live HTTP mode.
  - Asserts OpenMetadata context did not degrade (no OM fallback codes / missing-owner fallback).
  - Writes report JSON artifact.
- Helper module: `src/incident_copilot/live_validation.py`
- Tests: `tests/test_live_validation.py`

### Run Evidence
- Command:
  - `.venv/bin/python scripts/validate_live_openmetadata.py --replay runtime/fixtures/replay_event.json --output runtime/local_mirror/live_om_validation_report.json --service-hints demo_mysql`
- Result:
  - `Validation: ok`
  - `Seeded entity: demo_mysql.customer_analytics.raw.customer_profiles`
  - `Who acts first: admin via asset_owner`
  - `Fallback codes: ['SLACK_SEND_FAILED']`
- Report artifact:
  - `runtime/local_mirror/live_om_validation_report.json`

### Post-change Regression
- Full test suite:
  - `.venv/bin/python -m pytest -q` -> `92 passed`

---

## Seed-Create Extension (2026-04-19)

### Capability Upgrade
- `scripts/validate_live_openmetadata.py` now does create-if-missing bootstrap for:
  - database service
  - database
  - database schema
  - table
- It records bootstrap operations under `created_actions` in report JSON.

### Creation-Path Smoke Evidence
- Replay input:
  - `runtime/fixtures/replay_event_bootstrap_create.json`
  - entity FQN: `customer_analytics.raw.customer_profiles_bootstrap`
- Output:
  - `runtime/local_mirror/live_om_validation_report.bootstrap-create.json`
- Result:
  - `status = ok`
  - `seeded_entity_fqn = demo_mysql.customer_analytics.raw.customer_profiles_bootstrap`
  - `created_actions = ['created_table:demo_mysql.customer_analytics.raw.customer_profiles_bootstrap']`
  - `fallback_reason_codes = ['SLACK_SEND_FAILED']`

### Important Implementation Correction
- During bootstrap testing, OpenMetadata returned a `400` for table creation because `CreateTable.databaseSchema` expects a string FQN, not an object reference.
- Payloads were corrected to use string references for:
  - database service on database create
  - database on schema create
  - database schema on table create

### Final Regression Status
- Full test suite:
  - `.venv/bin/python -m pytest -q` -> `95 passed`
