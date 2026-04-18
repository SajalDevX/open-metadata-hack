# Metadata Incident Copilot — Expanded Design Spec

## Context

Defines the active incident-copilot design for the hackathon scope, covering six additional OpenMetadata problem statements while preserving deterministic demo guarantees.

- Primary theme: Data Observability (`2`)
- Supporting themes: MCP/AI Agents (`1`), Community & Comms (`5`), Governance & Classification (`6`)
- Covers: #26659 (RCA), #26658 (DQ Impact Scoring), #26660 (AI Recommendations), #26645 (Multi-MCP Orchestrator), #26609 (MCP Alert Tools), #26651 (Slack App)

## Problem

The base copilot produces a deterministic brief but:

1. "What failed" block gives no human-readable root cause — just a raw test message.
2. Impact ranking has no explainable score — judges and responders cannot see why an asset ranks higher.
3. "What to do next" is a static policy string — not tailored to the specific failure type.
4. The copilot is not composable — other agents and MCP clients cannot call its capabilities.

## Goal

Extend the 7-block base pipeline with 4 new blocks that cover all six problem statements, keeping demo flow within 2-5 minutes, preserving deterministic policy decisions, and adding Claude API only for narrative generation with explicit fallbacks.

## Approach

**Hybrid determinism model:**
- Deterministic: scoring formula, cause tree mapping, policy rules, owner routing, impact bounds.
- Claude API: RCA narrative (1-2 sentences from cause tree), "What to do next" bullets (from failure + profile context).
- Fallback guarantee: if any Claude call fails, template strings from the deterministic layer fill the block. No blank brief fields ever.

## Desired Prototype (Hackathon Cut)

For the hackathon, the prototype is successful only if one command can run a full incident flow and produce the same decision in repeat runs.

**Prototype-critical requirements (must ship):**
- Deterministic policy decision (`PII.Sensitive` => `approval_required`)
- RCA block always non-empty (Claude or fallback)
- Impact block with numeric score + reason string
- Action block with at least one recommendation bullet
- Parity output across Slack payload and local mirror
- Parity output across direct HTTP and `USE_OM_MCP=true` replay runs

**Nice-to-have (only after prototype is stable):**
- Richer recommendation prompt tuning
- Additional signal types beyond the initial 5
- Non-replay live metadata fetch hardening

## Integration Contract (How Components Combine)

Each component has one strict handoff contract. If this contract is broken, the pipeline is considered broken even if the demo still renders text.

1. `Context Resolver` -> `Impact Prioritizer`:
must return bounded impacted assets (depth <= 2, top <= 3) with classifications and ownership metadata.
2. `Impact Prioritizer` -> `Impact Scorer`:
must pass distance and downstream counts; scorer returns deterministic numeric score + score_reason.
3. `Context Resolver` -> `RCA Engine`:
must pass failed test payload; RCA returns non-empty narrative with explicit source (`claude` or `template`).
4. `Policy Advisor` -> `AI Recommender`:
policy state is authoritative; recommender may change wording, never policy decision.
5. `Brief Generator` -> `Delivery Layer`:
canonical brief payload is the single source for both Slack and local mirror rendering.
6. `Orchestrator` -> `MCP Facade`:
`triage_incident` must return the same canonical brief payload shape used by direct pipeline execution.

## Architecture — 11 Blocks

```
Raw Event
  → [1]  Adapter
  → [2]  Context Resolver       (optionally via OpenMetadata MCP server)
  → [3]  Impact Prioritizer     (depth ≤ 2, top ≤ 3)
  → [9]  Impact Scorer          ← NEW
  → [8]  RCA Engine             ← NEW
  → [4]  Policy Advisor         (PII.Sensitive → approval_required)
  → [10] AI Recommender         ← NEW
  → [5]  Brief Generator        (now receives scored assets + RCA narrative + AI next-step)
  → [6]  Delivery Layer         (Slack + local mirror)
  → [7]  Demo Harness

  [11]   MCP Facade             ← NEW (side-car: exposes + optionally consumes MCP)
```

Blocks 1–7 are unchanged. Blocks 8–11 are additive.

## New Component Specs

### [8] RCA Engine

**Covers:** #26659 — Human-readable explanations and root-cause traces for DQ checks

**Input:** `failed_test` dict from Context Resolver — includes test type, observed value, threshold, column name.

**Deterministic layer:**
Map signal type → cause tree node via rule table:

| Signal | Cause Tree Node |
|--------|----------------|
| `null_ratio_exceeded` | `data_completeness › upstream_null_propagation` |
| `format_mismatch` | `data_conformity › schema_drift` |
| `referential_break` | `data_integrity › upstream_delete_cascade` |
| `volume_drop` | `data_freshness › ingestion_lag` |
| `unknown` | `unclassified › manual_investigation_required` |

**Claude layer:**
Prompt: cause tree node + test message + column name + asset FQN.
Output: 1-2 sentence narrative for the "What failed" brief block.
Example: `"Null ratio on customer_id exceeded 15% threshold — likely caused by upstream null propagation from the orders pipeline."`

**Fallback:** If Claude call fails or times out (>3s), use cause tree node label as the narrative directly.

**Output contract:**
```python
@dataclass(frozen=True)
class RCAResult:
    cause_tree: list[str]        # e.g. ["data_completeness", "upstream_null_propagation"]
    narrative: str               # Claude-generated or template fallback
    narrative_source: str        # "claude" | "template"
    signal_type: str
```

---

### [9] Impact Scorer

**Covers:** #26658 — Data Quality Checks Impact (scoring model + explainability)

**Input:** Bounded impacted assets from Impact Prioritizer (max 3, depth ≤ 2).

**Scoring formula (deterministic):**
```
score = (business_facing × 3)
      + (pii_sensitive × 2)
      + (1.0 / distance)
      + log2(downstream_count + 1)
```

All terms are integers or floats derived from OpenMetadata metadata — no LLM involvement.

**Score reason string** (built alongside score, used in brief and MCP tool responses):
```
"business-facing +3, PII.Sensitive +2, distance=1 +1.0, downstream=4 +2.0 → 8.0"
```

**Judging criteria alignment:**
- Explainability: every score ships with a `score_reason` string.
- Robustness: formula is stable across usage pattern changes — `downstream_count` is the only dynamic term.

**Output contract:**
```python
@dataclass(frozen=True)
class ScoredAsset:
    fqn: str
    score: float
    score_reason: str
    classifications: list[str]
    business_facing: bool
    distance: int
```

---

### [10] AI Recommender

**Covers:** #26660 — AI-Powered Data Quality Recommendations

**Input:** `failed_test` type + top-scored asset column profile + `PolicyDecision`.

**Claude layer:**
Prompt includes: column type, test failure reason, classification tags, policy status.
Output: 2-3 bullet recommendations for the "What to do next" brief block.

Example output:
```
• Add a not_null check on customer_id with threshold 5%
• Investigate orders pipeline for null-emitting transformations
• Steward sign-off required before resuming downstream loads (PII.Sensitive)
```

**Fallback:** If Claude call fails, use the static policy string from Policy Advisor:
- `approval_required` → `"Escalate to data steward for approval before resuming downstream loads."`
- `allowed` → `"Proceed with manual remediation triage."`

**Determinism boundary:** Claude generates the narrative only. The `policy_state` field in the brief is always set by the deterministic Policy Advisor — never by Claude.

**Output contract:**
```python
@dataclass(frozen=True)
class RecommendationResult:
    bullets: list[str]
    source: str          # "claude" | "policy_fallback"
```

---

### [11] MCP Facade

**Covers:** #26645 (Multi-MCP Agent Orchestrator), #26609 (New MCP Alert/Notification Tools), #26651 (Slack App for OpenMetadata)

**Framework:** FastMCP (Python).

**Exposed MCP tools:**

| Tool | Input | Output |
|------|-------|--------|
| `triage_incident(incident_id, entity_fqn)` | Incident ID + asset FQN | 4-block brief + delivery metadata JSON |
| `score_impact(entity_fqn, lineage_depth)` | Asset FQN | List of `ScoredAsset` with score_reason |
| `get_rca(test_case_id, signal_type)` | Test case ID | `RCAResult` with cause tree + narrative |
| `notify_slack(incident_id)` | Incident ID | Delivery status (sent/failed/mirror) |

**OpenMetadata MCP consumption (optional):**
Context Resolver can be configured to call the OpenMetadata MCP server's `search_metadata` and lineage tools instead of direct HTTP. Toggle via `USE_OM_MCP=true` env var. Falls back to direct HTTP if MCP server unavailable.

**Multi-MCP pattern:**
The Facade acts as an orchestrator: `triage_incident` internally calls OpenMetadata MCP (context), runs the full pipeline, and calls Slack MCP (delivery). Composes 3 MCP servers in one tool call — matching the Multi-MCP Orchestrator problem statement.

---

## Updated Brief Structure

Each block now carries richer content:

| Block | Before | After |
|-------|--------|-------|
| What failed | Raw test message | RCA narrative (Claude or template) + cause tree refs |
| What is impacted | FQN list | FQN list + score + score_reason per asset |
| Who acts first | Owner via routing path | Unchanged |
| What to do next | Static policy string | AI recommendation bullets (Claude or policy fallback) |

## Deterministic Rules (unchanged from base)

All base rules preserved:
- Owner routing fallback: asset → domain → team → default channel
- Policy rule: `PII.Sensitive → approval_required`
- Impact bounds: depth ≤ 2, max 3 assets, business-facing first

## Reliability and Demo Safety (additions)

5. If Claude RCA call fails, `narrative_source = "template"` — brief still renders.
6. If Claude Recommender call fails, `source = "policy_fallback"` — brief still renders.
7. If OpenMetadata MCP unavailable, Context Resolver falls back to direct HTTP.
8. All Claude calls have a 3-second timeout with immediate fallback.
9. If Claude returns blank or unparsable text, treat as failure and use deterministic fallback.
10. One-click demo uses replay fixtures for both event and `om_data`; no hidden runtime state.

## Success Criteria (additions to base)

6. RCA narrative always present in "What failed" block — never empty.
7. Every impacted asset in brief has a numeric score and `score_reason` string.
8. "What to do next" block contains ≥ 1 bullet when Claude is available.
9. MCP Facade responds to `triage_incident` tool call and returns parity brief with Slack/local mirror.
10. `USE_OM_MCP=true` mode produces same brief as direct HTTP mode on replay fixture.
11. Slack payload and persisted local mirror share the same canonical core fields (parity checkable by hash or normalized JSON compare).
12. `triage_incident` MCP output on replay fixtures matches direct `run_pipeline` output for the same incident.

## Problem Statement Coverage Map

| Problem Statement | Issue | Covered by |
|---|---|---|
| Human-readable RCA explanations | #26659 | Block 8 — RCA Engine |
| DQ Checks Impact scoring | #26658 | Block 9 — Impact Scorer |
| AI-Powered DQ Recommendations | #26660 | Block 10 — AI Recommender |
| Multi-MCP Agent Orchestrator | #26645 | Block 11 — MCP Facade (compose pattern) |
| New MCP Alert/Notification Tools | #26609 | Block 11 — `notify_slack` MCP tool |
| Slack App for OpenMetadata | #26651 | Block 11 — `notify_slack` + Slack MCP integration |

## Tech Stack Additions

- `openai` SDK (OpenRouter mode) — LLM calls in blocks 8 and 10 via OpenRouter's OpenAI-compatible API
- `fastmcp` — MCP server for block 11
- All new blocks: Python 3.14, dataclasses, pytest, no new external deps beyond these two
