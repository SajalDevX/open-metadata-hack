# Prototype Progress Reference

Last updated: 2026-04-19
Scope source:
- `2026-04-18-metadata-incident-copilot-design.md` (base 7-block prototype)
- `2026-04-18-metadata-incident-copilot-expanded-design.md` (11-block final prototype)

## Overall Snapshot

- Completed: core deterministic triage pipeline, OpenMetadata live replay integration, FQN mapping hardening, bootstrap validator automation, MCP transport + facade coverage, Slack sender wiring + fallback behavior.
- In progress: converting all expanded-spec "prototype-critical requirements" into one stable end-to-end demo command and checklist artifact.
- Remaining: deeper lineage/impact realism, explicit parity checks for MCP mode vs HTTP mode on same replay inputs, final packaging/demo-runbook polish.

## Workstream Checklist (Whole Prototype)

### 1) Base 7-Block Pipeline

- [x] Adapter (normalize incident payload + fallback reason handling)
- [x] Context Resolver (fixture + direct HTTP + MCP transport path)
- [x] Impact Prioritizer (depth <= 2, top <= 3)
- [x] Policy Advisor (`PII.Sensitive` => `approval_required`)
- [x] Brief Generator (canonical 4-block structure)
- [x] Delivery Layer (Slack + local mirror fallback)
- [x] Demo Harness (replay-driven deterministic flow)

Status: Completed for hackathon cut.

### 2) Expanded 11-Block Additions

- [x] RCA Engine integrated (non-empty RCA block via Claude/template fallback contract)
- [x] Impact Scorer integrated (numeric score + score_reason)
- [x] AI Recommender integrated (recommendation bullets with fallback source)
- [x] MCP Facade integrated (triage/score/get_rca/notify tool surface)

Status: Implemented in codebase; remaining item is final parity proof packaging (see remaining section).

### 3) OpenMetadata Integration Hardening

- [x] Live OM auth + context fetch validation
- [x] Fixture 3-part FQN -> service-prefixed FQN mapping support
- [x] Resolver fallback-chain tests (`MCP -> HTTP -> fixture`)
- [x] One-shot live validator (seed-check + replay + no-OM-fallback assertion)
- [x] Seed-create-if-missing extension (service/database/schema/table)
- [x] Creation-path smoke run with report including `created_actions`

Status: Completed for local validation environment.

### 4) Testing and Verification

- [x] Focused red/green tests for resolver + OM client + validation helpers
- [x] Full regression suite green after hardening changes
- [x] Latest full run: `95 passed`

Status: Completed for current branch.

### 5) Documentation/Tracking

- [x] Incremental task log updates in `tasks/todo.md`
- [x] Validation evidence notes in `tasks/openmetadata-live-validation-2026-04-19.md`
- [x] Lessons captured in `tasks/lessons.md`
- [x] This consolidated reference file added

Status: Completed.

## Prototype-Critical Requirement Mapping

From expanded spec "Prototype-critical requirements (must ship)":

1. Deterministic policy decision (`PII.Sensitive` => `approval_required`)
- Status: [x] Done

2. RCA block always non-empty (Claude or fallback)
- Status: [x] Done

3. Impact block with numeric score + reason string
- Status: [x] Done

4. Action block with at least one recommendation bullet
- Status: [x] Done

5. Parity output across Slack payload and local mirror
- Status: [~] Partial
- Why partial: delivery logic and tests exist; still need one explicit published artifact/checklist run for final demo evidence bundle.

6. Parity output across direct HTTP and `USE_OM_MCP=true` replay runs
- Status: [~] Partial
- Why partial: transport paths and fallback behavior are implemented/tested; still need a single explicit side-by-side parity assertion artifact for final prototype sign-off.

## What Is Still Remaining

### A) Final Demo-Parity Evidence

- [ ] Add one script/check that runs the same replay in:
  - direct HTTP mode
  - `USE_OM_MCP=true` mode
  and compares normalized canonical brief fields.
- [ ] Save parity report artifact under `runtime/local_mirror/` and reference it from task notes.

### B) Impact Realism (Quality Improvement)

- [ ] Seed richer lineage graph (multiple downstream nodes) so `what_is_impacted` and score ordering are visibly non-trivial in demo output.
- [ ] Add one reproducible fixture+seed pair that reliably demonstrates ranking explanation (`score_reason`) with >1 impacted asset.

### C) Slack Surface Completion

- [ ] Decide final Slack mode for demo (real webhook vs mirror-only).
- [ ] If real webhook is used, add one deterministic dry-run/smoke checklist that validates payload parity without manual edits.

### D) Final Runbook Polish

- [ ] Add concise "single command + expected outputs" section in README/task note for judges.
- [ ] Attach final artifact list (brief output, validation report, parity report, test summary).

## Recommended Next Order (Shortest Path to Final Prototype Sign-off)

1. Build HTTP vs MCP parity report script/check.
2. Seed richer lineage demo scenario and record one non-trivial impact report.
3. Finalize Slack decision and capture one deterministic evidence run.
4. Publish final runbook section and evidence index.

## Reference Artifacts

- Live validation note:
  - `projects/main-submission/tasks/openmetadata-live-validation-2026-04-19.md`
- One-shot validation reports:
  - `projects/main-submission/runtime/local_mirror/live_om_validation_report.json`
  - `projects/main-submission/runtime/local_mirror/live_om_validation_report.bootstrap.json`
  - `projects/main-submission/runtime/local_mirror/live_om_validation_report.bootstrap-create.json`
- Task log:
  - `projects/main-submission/tasks/todo.md`
