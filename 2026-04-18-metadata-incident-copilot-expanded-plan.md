# Metadata Incident Copilot — Expanded Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 4 new blocks (RCA Engine, Impact Scorer, AI Recommender, MCP Facade) to the existing incident copilot, covering hackathon problem statements #26659, #26658, #26660, #26645, #26609, #26651.

**Architecture:** New blocks insert into the existing orchestrator pipeline between Impact Prioritizer and Brief Generator. All Claude API calls go through OpenRouter using the `openai` SDK. Every Claude call has a 3-second timeout and a deterministic template fallback so the demo never produces blank brief fields.

**Tech Stack:** Python 3.14, `openai` SDK (OpenRouter), `fastmcp`, pytest, dataclasses. Existing stack unchanged.

---

## References

- Base spec: `2026-04-18-metadata-incident-copilot-design.md`
- Expanded spec: `2026-04-18-metadata-incident-copilot-expanded-design.md`
- Base plan: `2026-04-18-metadata-incident-copilot.md`
- Apply DRY, YAGNI, TDD, and frequent commits.

## Planned File Structure

### Create

- `projects/main-submission/src/incident_copilot/openrouter_client.py` — shared OpenRouter client factory + availability check
- `projects/main-submission/src/incident_copilot/rca_engine.py` — Block 8: signal → cause tree → narrative
- `projects/main-submission/src/incident_copilot/impact_scorer.py` — Block 9: deterministic asset scoring formula
- `projects/main-submission/src/incident_copilot/ai_recommender.py` — Block 10: Claude-powered next-step bullets
- `projects/main-submission/src/incident_copilot/mcp_facade.py` — Block 11: FastMCP server exposing 4 tools
- `projects/main-submission/tests/test_openrouter_client.py`
- `projects/main-submission/tests/test_rca_engine.py`
- `projects/main-submission/tests/test_impact_scorer.py`
- `projects/main-submission/tests/test_ai_recommender.py`
- `projects/main-submission/tests/test_mcp_facade.py`

### Modify

- `projects/main-submission/src/incident_copilot/contracts.py` — add `RCAResult`, `ScoredAsset`, `RecommendationResult`
- `projects/main-submission/src/incident_copilot/orchestrator.py` — wire blocks 8, 9, 10 into pipeline
- `projects/main-submission/src/incident_copilot/context_resolver.py` — add `USE_OM_MCP=true` switch with direct-HTTP fallback
- `projects/main-submission/tests/test_context_resolver.py` — add resolver mode parity + MCP-unavailable fallback coverage
- `projects/main-submission/pyproject.toml` — add `openai` and `fastmcp` dependencies
- `projects/main-submission/src/incident_copilot/delivery.py` — expose canonical payload/hash for Slack vs local mirror parity checks
- `projects/main-submission/scripts/run_demo.py` — add one-click deterministic replay entrypoint with optional `--use-om-mcp`
- `projects/main-submission/runtime/fixtures/replay_om_context.json` — explicit demo context source of truth for `om_data`

---

## Prototype Strategy (Build This First)

This is the strategic path to the desired hackathon prototype. Do not optimize for feature count until this path is green.

**Phase 0: Reproducible demo envelope**
- Lock replay event + replay OM context fixtures
- Ensure one command can run full pipeline and render output
- Exit gate: two consecutive runs produce identical local mirror output

**Phase 1: Deterministic decision core**
- Contracts + impact scorer + policy decision + brief formatting
- Exit gate: `PII.Sensitive` case always results in `approval_required`

**Phase 2: Explainability and recommendations**
- RCA engine + AI recommender with strict fallback behavior
- Exit gate: RCA and recommendation blocks are always non-empty without API key

**Phase 3: Integration and parity proof**
- Orchestrator wiring + MCP facade + delivery parity checks + resolver mode parity
- Exit gate: direct HTTP vs `USE_OM_MCP=true` parity and Slack vs local mirror parity both pass

**Critical path for judging demo:**
`Task 1 -> Task 3 -> Task 4 -> Task 6 -> Task 8`

**Rule for scope pressure:**
If time is short, cut breadth (new signals, richer prompts), never cut parity or fallback guarantees.

---

### Task 1: Add Dependencies and Extend Contracts

**Files:**
- Modify: `projects/main-submission/pyproject.toml`
- Modify: `projects/main-submission/src/incident_copilot/contracts.py`
- Test: `projects/main-submission/tests/test_contracts.py`

- [ ] **Step 1: Add dependencies to pyproject.toml**

Replace the `[project]` section in `projects/main-submission/pyproject.toml`:

```toml
[project]
name = "metadata-incident-copilot"
version = "0.2.0"
requires-python = ">=3.14"
dependencies = [
    "openai>=1.0.0",
    "fastmcp>=0.1.0",
]

[tool.pytest.ini_options]
pythonpath = ["src"]
```

- [ ] **Step 2: Write failing contract tests for new types**

Add to `projects/main-submission/tests/test_contracts.py`:

```python
from incident_copilot.contracts import RCAResult, ScoredAsset, RecommendationResult

def test_rca_result_fields():
    r = RCAResult(
        cause_tree=["data_completeness", "upstream_null_propagation"],
        narrative="Null ratio exceeded threshold.",
        narrative_source="template",
        signal_type="null_ratio_exceeded",
    )
    assert r.cause_tree[0] == "data_completeness"
    assert r.narrative_source == "template"

def test_scored_asset_fields():
    a = ScoredAsset(
        fqn="svc.db.orders",
        score=8.0,
        score_reason="business-facing +3.0, PII.Sensitive +2.0 → 8.0",
        classifications=["PII.Sensitive"],
        business_facing=True,
        distance=1,
    )
    assert a.score == 8.0
    assert "PII.Sensitive" in a.classifications

def test_recommendation_result_fields():
    r = RecommendationResult(
        bullets=["Check upstream pipeline", "Notify owner"],
        source="claude",
    )
    assert len(r.bullets) == 2
    assert r.source == "claude"
```

- [ ] **Step 3: Run tests to verify failure**

Run: `python -m pytest projects/main-submission/tests/test_contracts.py::test_rca_result_fields projects/main-submission/tests/test_contracts.py::test_scored_asset_fields projects/main-submission/tests/test_contracts.py::test_recommendation_result_fields -v`
Expected: `FAIL` with ImportError.

- [ ] **Step 4: Add new dataclasses to contracts.py**

Append to `projects/main-submission/src/incident_copilot/contracts.py`:

```python
@dataclass(frozen=True)
class RCAResult:
    cause_tree: list[str]
    narrative: str
    narrative_source: str  # "claude" | "template"
    signal_type: str

@dataclass(frozen=True)
class ScoredAsset:
    fqn: str
    score: float
    score_reason: str
    classifications: list[str]
    business_facing: bool
    distance: int

@dataclass(frozen=True)
class RecommendationResult:
    bullets: list[str]
    source: str  # "claude" | "policy_fallback"
```

- [ ] **Step 5: Run tests to verify pass**

Run: `python -m pytest projects/main-submission/tests/test_contracts.py -v`
Expected: all `PASS`.

- [ ] **Step 6: Commit**

```bash
git add projects/main-submission/pyproject.toml \
  projects/main-submission/src/incident_copilot/contracts.py \
  projects/main-submission/tests/test_contracts.py
git commit -m "feat: add RCAResult, ScoredAsset, RecommendationResult contracts and openai/fastmcp deps"
```

---

### Task 2: OpenRouter Client

**Files:**
- Create: `projects/main-submission/src/incident_copilot/openrouter_client.py`
- Test: `projects/main-submission/tests/test_openrouter_client.py`

- [ ] **Step 1: Write failing tests**

Create `projects/main-submission/tests/test_openrouter_client.py`:

```python
import os
from unittest.mock import patch
from incident_copilot.openrouter_client import get_client, is_available

def test_is_available_false_when_no_key():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("OPENROUTER_API_KEY", None)
        assert is_available() is False

def test_is_available_true_when_key_set():
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test"}):
        assert is_available() is True

def test_get_client_returns_openai_client():
    from openai import OpenAI
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test"}):
        client = get_client()
        assert isinstance(client, OpenAI)
        assert str(client.base_url).startswith("https://openrouter.ai/")
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest projects/main-submission/tests/test_openrouter_client.py -v`
Expected: `FAIL` with ImportError.

- [ ] **Step 3: Implement client module**

Create `projects/main-submission/src/incident_copilot/openrouter_client.py`:

```python
import os
from openai import OpenAI

def is_available() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY"))

def get_client() -> OpenAI:
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
    )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest projects/main-submission/tests/test_openrouter_client.py -v`
Expected: all `PASS`.

- [ ] **Step 5: Commit**

```bash
git add projects/main-submission/src/incident_copilot/openrouter_client.py \
  projects/main-submission/tests/test_openrouter_client.py
git commit -m "feat: add OpenRouter client with availability check"
```

---

### Task 3: RCA Engine (Block 8)

**Files:**
- Create: `projects/main-submission/src/incident_copilot/rca_engine.py`
- Test: `projects/main-submission/tests/test_rca_engine.py`

- [ ] **Step 1: Write failing tests**

Create `projects/main-submission/tests/test_rca_engine.py`:

```python
import os
from unittest.mock import patch
from incident_copilot.rca_engine import infer_signal_type, build_rca

def test_infer_null_signal():
    assert infer_signal_type({"message": "null ratio exceeded 15%"}) == "null_ratio_exceeded"

def test_infer_format_signal():
    assert infer_signal_type({"message": "format mismatch detected"}) == "format_mismatch"

def test_infer_referential_signal():
    assert infer_signal_type({"message": "referential integrity broken"}) == "referential_break"

def test_infer_volume_signal():
    assert infer_signal_type({"message": "volume drop detected"}) == "volume_drop"

def test_infer_unknown_signal():
    assert infer_signal_type({"message": "something weird happened"}) == "unknown"

def test_build_rca_template_fallback_when_no_key():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("OPENROUTER_API_KEY", None)
        result = build_rca({"message": "null ratio exceeded 15%"}, "svc.db.orders")
        assert result.signal_type == "null_ratio_exceeded"
        assert result.cause_tree == ["data_completeness", "upstream_null_propagation"]
        assert result.narrative_source == "template"
        assert result.narrative != ""

def test_build_rca_cause_tree_for_unknown():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("OPENROUTER_API_KEY", None)
        result = build_rca({"message": "???"}, "svc.db.orders")
        assert result.signal_type == "unknown"
        assert "unclassified" in result.cause_tree

def test_build_rca_uses_claude_when_key_available():
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test"}):
        with patch("incident_copilot.rca_engine._claude_narrative", return_value="Claude says: null upstream.") as mock_claude:
            result = build_rca({"message": "null ratio exceeded"}, "svc.db.orders")
            mock_claude.assert_called_once()
            assert result.narrative == "Claude says: null upstream."
            assert result.narrative_source == "claude"

def test_build_rca_falls_back_to_template_when_claude_raises():
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test"}):
        with patch("incident_copilot.rca_engine._claude_narrative", side_effect=Exception("timeout")):
            result = build_rca({"message": "null ratio exceeded"}, "svc.db.orders")
            assert result.narrative_source == "template"
            assert result.narrative != ""
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest projects/main-submission/tests/test_rca_engine.py -v`
Expected: `FAIL` with ImportError.

- [ ] **Step 3: Implement RCA Engine**

Create `projects/main-submission/src/incident_copilot/rca_engine.py`:

```python
from incident_copilot.contracts import RCAResult
from incident_copilot.openrouter_client import is_available, get_client

SIGNAL_MAP: dict[str, list[str]] = {
    "null_ratio_exceeded": ["data_completeness", "upstream_null_propagation"],
    "format_mismatch": ["data_conformity", "schema_drift"],
    "referential_break": ["data_integrity", "upstream_delete_cascade"],
    "volume_drop": ["data_freshness", "ingestion_lag"],
    "unknown": ["unclassified", "manual_investigation_required"],
}

TEMPLATE_NARRATIVES: dict[str, str] = {
    "null_ratio_exceeded": "Null ratio exceeded threshold — likely caused by upstream null propagation.",
    "format_mismatch": "Format mismatch detected — likely caused by schema drift in source data.",
    "referential_break": "Referential integrity broken — likely caused by upstream delete cascade.",
    "volume_drop": "Volume drop detected — likely caused by ingestion lag or pipeline failure.",
    "unknown": "Unclassified failure — manual investigation required.",
}


def infer_signal_type(failed_test: dict) -> str:
    msg = (failed_test.get("message") or "").lower()
    test_type = (failed_test.get("testType") or "").lower()
    combined = msg + " " + test_type
    if "null" in combined:
        return "null_ratio_exceeded"
    if "format" in combined:
        return "format_mismatch"
    if "referential" in combined or "foreign" in combined:
        return "referential_break"
    if "volume" in combined or "count" in combined:
        return "volume_drop"
    return "unknown"


def build_rca(failed_test: dict, entity_fqn: str, use_ai: bool = True) -> RCAResult:
    signal = infer_signal_type(failed_test)
    cause_tree = SIGNAL_MAP[signal]
    narrative = None
    source = "template"

    if use_ai and is_available():
        try:
            narrative = _claude_narrative(signal, cause_tree, failed_test, entity_fqn)
            source = "claude"
        except Exception:
            pass

    if narrative is None:
        narrative = TEMPLATE_NARRATIVES[signal]

    return RCAResult(
        cause_tree=cause_tree,
        narrative=narrative,
        narrative_source=source,
        signal_type=signal,
    )


def _claude_narrative(signal: str, cause_tree: list[str], failed_test: dict, entity_fqn: str) -> str:
    client = get_client()
    prompt = (
        f"A data quality check failed on asset '{entity_fqn}'.\n"
        f"Test message: {failed_test.get('message', 'unknown')}\n"
        f"Root cause category: {' > '.join(cause_tree)}\n"
        f"Write 1-2 sentences explaining what failed and why, in plain English for a data engineer."
    )
    resp = client.chat.completions.create(
        model="anthropic/claude-haiku-4-5",
        max_tokens=128,
        timeout=3,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip()
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest projects/main-submission/tests/test_rca_engine.py -v`
Expected: all `PASS`.

- [ ] **Step 5: Commit**

```bash
git add projects/main-submission/src/incident_copilot/rca_engine.py \
  projects/main-submission/tests/test_rca_engine.py
git commit -m "feat: add RCA engine with signal mapping and Claude narrative fallback"
```

---

### Task 4: Impact Scorer (Block 9)

**Files:**
- Create: `projects/main-submission/src/incident_copilot/impact_scorer.py`
- Test: `projects/main-submission/tests/test_impact_scorer.py`

- [ ] **Step 1: Write failing tests**

Create `projects/main-submission/tests/test_impact_scorer.py`:

```python
import math
from incident_copilot.impact_scorer import score_asset, score_assets

def test_business_facing_adds_three():
    asset = {"fqn": "a", "business_facing": True, "distance": 1, "downstream_count": 0, "classifications": []}
    result = score_asset(asset)
    assert result.score >= 3.0

def test_pii_sensitive_adds_two():
    asset = {"fqn": "a", "business_facing": False, "distance": 1, "downstream_count": 0, "classifications": ["PII.Sensitive"]}
    result = score_asset(asset)
    assert result.score >= 2.0

def test_score_reason_contains_all_terms():
    asset = {"fqn": "a", "business_facing": True, "distance": 1, "downstream_count": 4, "classifications": ["PII.Sensitive"]}
    result = score_asset(asset)
    assert "business-facing" in result.score_reason
    assert "PII.Sensitive" in result.score_reason
    assert "distance=1" in result.score_reason
    assert "downstream=4" in result.score_reason

def test_score_formula_correctness():
    asset = {"fqn": "a", "business_facing": True, "distance": 1, "downstream_count": 4, "classifications": ["PII.Sensitive"]}
    result = score_asset(asset)
    expected = round(3.0 + 2.0 + 1.0 / 1 + math.log2(4 + 1), 2)
    assert result.score == expected

def test_score_assets_sorted_descending():
    assets = [
        {"fqn": "low", "business_facing": False, "distance": 2, "downstream_count": 0, "classifications": []},
        {"fqn": "high", "business_facing": True, "distance": 1, "downstream_count": 4, "classifications": ["PII.Sensitive"]},
    ]
    result = score_assets(assets)
    assert result[0].fqn == "high"

def test_fqn_and_classifications_preserved():
    asset = {"fqn": "svc.db.orders", "business_facing": False, "distance": 1, "downstream_count": 0, "classifications": ["Finance.Internal"]}
    result = score_asset(asset)
    assert result.fqn == "svc.db.orders"
    assert result.classifications == ["Finance.Internal"]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest projects/main-submission/tests/test_impact_scorer.py -v`
Expected: `FAIL` with ImportError.

- [ ] **Step 3: Implement Impact Scorer**

Create `projects/main-submission/src/incident_copilot/impact_scorer.py`:

```python
import math
from incident_copilot.contracts import ScoredAsset


def score_asset(asset: dict) -> ScoredAsset:
    business_facing = bool(asset.get("business_facing", False))
    pii_sensitive = "PII.Sensitive" in (asset.get("classifications") or [])
    distance = asset.get("distance", 1)
    downstream_count = asset.get("downstream_count", 0)

    bf_score = 3.0 if business_facing else 0.0
    pii_score = 2.0 if pii_sensitive else 0.0
    dist_score = round(1.0 / distance, 2)
    ds_score = round(math.log2(downstream_count + 1), 2)
    total = round(bf_score + pii_score + dist_score + ds_score, 2)

    parts = []
    if business_facing:
        parts.append("business-facing +3.0")
    if pii_sensitive:
        parts.append("PII.Sensitive +2.0")
    parts.append(f"distance={distance} +{dist_score}")
    parts.append(f"downstream={downstream_count} +{ds_score}")
    parts.append(f"→ {total}")

    return ScoredAsset(
        fqn=asset.get("fqn", ""),
        score=total,
        score_reason=", ".join(parts),
        classifications=asset.get("classifications") or [],
        business_facing=business_facing,
        distance=distance,
    )


def score_assets(assets: list[dict]) -> list[ScoredAsset]:
    return sorted([score_asset(a) for a in assets], key=lambda x: x.score, reverse=True)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest projects/main-submission/tests/test_impact_scorer.py -v`
Expected: all `PASS`.

- [ ] **Step 5: Commit**

```bash
git add projects/main-submission/src/incident_copilot/impact_scorer.py \
  projects/main-submission/tests/test_impact_scorer.py
git commit -m "feat: add deterministic impact scorer with explainable score_reason"
```

---

### Task 5: AI Recommender (Block 10)

**Files:**
- Create: `projects/main-submission/src/incident_copilot/ai_recommender.py`
- Test: `projects/main-submission/tests/test_ai_recommender.py`

- [ ] **Step 1: Write failing tests**

Create `projects/main-submission/tests/test_ai_recommender.py`:

```python
import os
from unittest.mock import patch
from incident_copilot.contracts import PolicyDecision, ScoredAsset
from incident_copilot.ai_recommender import recommend

ALLOWED_POLICY = PolicyDecision(
    incident_id="inc-1", status="allowed", reason_codes=[], required_approver_role=None
)
APPROVAL_POLICY = PolicyDecision(
    incident_id="inc-1", status="approval_required",
    reason_codes=["PII_SENSITIVE_IMPACTED"], required_approver_role="data_steward"
)
TOP_ASSET = ScoredAsset(
    fqn="svc.db.orders", score=8.0,
    score_reason="business-facing +3.0 → 8.0",
    classifications=["PII.Sensitive"], business_facing=True, distance=1
)

def test_policy_fallback_when_no_key():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("OPENROUTER_API_KEY", None)
        result = recommend({"message": "null ratio exceeded"}, TOP_ASSET, ALLOWED_POLICY)
        assert result.source == "policy_fallback"
        assert len(result.bullets) >= 1

def test_approval_required_fallback_mentions_steward():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("OPENROUTER_API_KEY", None)
        result = recommend({"message": "null ratio exceeded"}, TOP_ASSET, APPROVAL_POLICY)
        assert result.source == "policy_fallback"
        assert any("steward" in b.lower() for b in result.bullets)

def test_uses_claude_when_key_available():
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test"}):
        with patch("incident_copilot.ai_recommender._claude_recommend", return_value=["Check upstream", "Notify owner"]):
            result = recommend({"message": "null ratio"}, TOP_ASSET, ALLOWED_POLICY)
            assert result.source == "claude"
            assert result.bullets == ["Check upstream", "Notify owner"]

def test_falls_back_when_claude_raises():
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test"}):
        with patch("incident_copilot.ai_recommender._claude_recommend", side_effect=Exception("timeout")):
            result = recommend({"message": "null ratio"}, TOP_ASSET, ALLOWED_POLICY)
            assert result.source == "policy_fallback"
            assert len(result.bullets) >= 1

def test_policy_fallback_when_no_asset():
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test"}):
        result = recommend({"message": "null ratio"}, None, ALLOWED_POLICY)
        assert result.source == "policy_fallback"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest projects/main-submission/tests/test_ai_recommender.py -v`
Expected: `FAIL` with ImportError.

- [ ] **Step 3: Implement AI Recommender**

Create `projects/main-submission/src/incident_copilot/ai_recommender.py`:

```python
from incident_copilot.contracts import PolicyDecision, RecommendationResult, ScoredAsset
from incident_copilot.openrouter_client import is_available, get_client

POLICY_FALLBACKS: dict[str, list[str]] = {
    "approval_required": [
        "Escalate to data steward for approval before resuming downstream loads.",
        "Do not process downstream assets until steward sign-off is confirmed.",
    ],
    "allowed": [
        "Proceed with manual remediation triage.",
        "Notify asset owner to investigate the root cause.",
    ],
}


def recommend(
    failed_test: dict,
    top_asset: ScoredAsset | None,
    policy: PolicyDecision,
) -> RecommendationResult:
    if is_available() and top_asset is not None:
        try:
            bullets = _claude_recommend(failed_test, top_asset, policy)
            return RecommendationResult(bullets=bullets, source="claude")
        except Exception:
            pass
    return RecommendationResult(
        bullets=POLICY_FALLBACKS.get(policy.status, POLICY_FALLBACKS["allowed"]),
        source="policy_fallback",
    )


def _claude_recommend(
    failed_test: dict,
    top_asset: ScoredAsset,
    policy: PolicyDecision,
) -> list[str]:
    client = get_client()
    classifications = ", ".join(top_asset.classifications) if top_asset.classifications else "none"
    prompt = (
        f"A data quality check failed.\n"
        f"Test failure: {failed_test.get('message', 'unknown')}\n"
        f"Affected asset: {top_asset.fqn} (classifications: {classifications})\n"
        f"Policy status: {policy.status}\n"
        f"List 2-3 specific next steps for the data engineer. "
        f"Use bullet points starting with •. Be concise."
    )
    resp = client.chat.completions.create(
        model="anthropic/claude-haiku-4-5",
        max_tokens=200,
        timeout=3,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.choices[0].message.content.strip()
    bullets = [line.strip().lstrip("•-").strip() for line in raw.splitlines() if line.strip()]
    return [b for b in bullets if b][:3]
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest projects/main-submission/tests/test_ai_recommender.py -v`
Expected: all `PASS`.

- [ ] **Step 5: Commit**

```bash
git add projects/main-submission/src/incident_copilot/ai_recommender.py \
  projects/main-submission/tests/test_ai_recommender.py
git commit -m "feat: add AI recommender with policy fallback for What-to-do-next block"
```

---

### Task 6: Wire New Blocks into Orchestrator

**Files:**
- Modify: `projects/main-submission/src/incident_copilot/orchestrator.py`
- Test: `projects/main-submission/tests/test_orchestrator.py`

- [ ] **Step 1: Write failing tests for expanded orchestrator output**

Add to `projects/main-submission/tests/test_orchestrator.py`:

```python
import os
from unittest.mock import patch
from incident_copilot.orchestrator import run_pipeline

RAW = {
    "incident_id": "inc-1", "entity_fqn": "svc.db.customer_profiles",
    "test_case_id": "tc-1", "severity": "high",
    "occurred_at": "2026-04-18T00:00:00Z", "raw_ref": "evt-1",
}
OM_DATA = {
    "failed_test": {"message": "null ratio exceeded 15%"},
    "lineage": [{"fqn": "svc.db.customer_curated", "distance": 1, "business_facing": True,
                 "downstream_count": 3, "owner": "dre-oncall"}],
    "owners": {"asset_owner": "dre-oncall"},
    "classifications": {"svc.db.customer_curated": ["PII.Sensitive"]},
}

def test_pipeline_returns_rca_result():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("OPENROUTER_API_KEY", None)
        out = run_pipeline(RAW, OM_DATA, slack_sender=lambda _: True)
        assert "rca" in out
        assert out["rca"].signal_type == "null_ratio_exceeded"
        assert out["rca"].narrative != ""

def test_pipeline_returns_scored_assets():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("OPENROUTER_API_KEY", None)
        out = run_pipeline(RAW, OM_DATA, slack_sender=lambda _: True)
        assert "scored_assets" in out
        assert len(out["scored_assets"]) == 1
        assert out["scored_assets"][0].fqn == "svc.db.customer_curated"
        assert out["scored_assets"][0].score > 0

def test_pipeline_returns_recommendation():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("OPENROUTER_API_KEY", None)
        out = run_pipeline(RAW, OM_DATA, slack_sender=lambda _: True)
        assert "recommendation" in out
        assert len(out["recommendation"].bullets) >= 1

def test_brief_what_failed_contains_rca_narrative():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("OPENROUTER_API_KEY", None)
        out = run_pipeline(RAW, OM_DATA, slack_sender=lambda _: True)
        assert "null" in out["brief"]["what_failed"]["text"].lower()

def test_brief_what_is_impacted_contains_score():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("OPENROUTER_API_KEY", None)
        out = run_pipeline(RAW, OM_DATA, slack_sender=lambda _: True)
        assert "score:" in out["brief"]["what_is_impacted"]["text"]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest projects/main-submission/tests/test_orchestrator.py::test_pipeline_returns_rca_result projects/main-submission/tests/test_orchestrator.py::test_pipeline_returns_scored_assets projects/main-submission/tests/test_orchestrator.py::test_pipeline_returns_recommendation -v`
Expected: `FAIL` — `rca`, `scored_assets`, `recommendation` keys missing from output.

- [ ] **Step 3: Replace orchestrator.py with expanded version**

Overwrite `projects/main-submission/src/incident_copilot/orchestrator.py`:

```python
from incident_copilot.adapter import normalize_event
from incident_copilot.context_resolver import resolve_context
from incident_copilot.owner_routing import resolve_first_responder
from incident_copilot.impact import select_top_impacted_assets
from incident_copilot.impact_scorer import score_assets
from incident_copilot.rca_engine import build_rca
from incident_copilot.policy import evaluate_policy
from incident_copilot.ai_recommender import recommend
from incident_copilot.brief import build_incident_brief
from incident_copilot.delivery import deliver

_DEFAULT_MIRROR = "projects/main-submission/runtime/local_mirror/latest_brief.json"


def run_pipeline(raw_event, om_data, slack_sender, mirror_writer=lambda _p: _DEFAULT_MIRROR):
    env = normalize_event(raw_event)
    ctx = resolve_context(env, om_data, max_depth=2)

    impacted = select_top_impacted_assets(ctx["impacted_assets"], max_assets=3, max_depth=2)
    scored = score_assets(impacted)
    rca = build_rca(ctx["failed_test"], env.get("entity_fqn", ""), use_ai=True)
    policy = evaluate_policy(env["incident_id"], impacted)
    top_asset = scored[0] if scored else None
    recommendation = recommend(ctx["failed_test"], top_asset, policy)

    first_actor, first_path = resolve_first_responder(
        ctx["owners"].get("asset_owner"),
        ctx["owners"].get("domain_owner"),
        ctx["owners"].get("team_owner"),
        "#metadata-incidents",
    )

    brief = build_incident_brief(
        incident_id=env["incident_id"],
        what_failed=(
            rca.narrative,
            ["incident_ref", "test_ref", f"rca:{rca.signal_type}"],
        ),
        what_is_impacted=(
            ", ".join(f"{a.fqn} (score:{a.score})" for a in scored) or "none",
            ["lineage_ref"] + [f"score:{a.fqn}" for a in scored],
        ),
        who_acts_first=(f"{first_actor} via {first_path}", ["owner_ref"]),
        what_to_do_next=(
            "\n".join(f"• {b}" for b in recommendation.bullets),
            ["policy_ref", "classification_ref"]
            if policy.status == "approval_required"
            else ["policy_ref"],
        ),
        policy_state=policy.status,
    )

    delivery_result = deliver(brief, slack_sender, mirror_writer)

    return {
        "brief": brief,
        "delivery": delivery_result,
        "rca": rca,
        "scored_assets": scored,
        "recommendation": recommendation,
        "fallback_reason_codes": (
            env["fallback_reason_codes"]
            + ctx["fallback_reason_codes"]
            + (delivery_result["delivery"].degraded_reason_codes or [])
        ),
    }
```

- [ ] **Step 4: Run full orchestrator test suite**

Run: `python -m pytest projects/main-submission/tests/test_orchestrator.py -v`
Expected: all `PASS`.

- [ ] **Step 5: Commit**

```bash
git add projects/main-submission/src/incident_copilot/orchestrator.py \
  projects/main-submission/tests/test_orchestrator.py
git commit -m "feat: wire RCA engine, impact scorer, and AI recommender into orchestrator pipeline"
```

---

### Task 7: MCP Facade (Block 11)

**Files:**
- Create: `projects/main-submission/src/incident_copilot/mcp_facade.py`
- Test: `projects/main-submission/tests/test_mcp_facade.py`

- [ ] **Step 1: Write failing tests**

Create `projects/main-submission/tests/test_mcp_facade.py`:

```python
from incident_copilot.mcp_facade import get_rca_tool, score_impact_tool, notify_slack_tool

def test_get_rca_returns_cause_tree_and_narrative():
    result = get_rca_tool(test_case_id="tc-null-1", signal_type="null_ratio_exceeded")
    assert "cause_tree" in result
    assert result["cause_tree"] == ["data_completeness", "upstream_null_propagation"]
    assert result["narrative"] != ""
    assert result["signal_type"] == "null_ratio_exceeded"

def test_get_rca_unknown_signal():
    result = get_rca_tool(test_case_id="tc-unknown", signal_type="unknown")
    assert "unclassified" in result["cause_tree"]

def test_score_impact_returns_list():
    result = score_impact_tool(entity_fqn="svc.db.orders", lineage_depth=2)
    assert isinstance(result, list)

def test_notify_slack_returns_status_dict():
    result = notify_slack_tool(incident_id="inc-1")
    assert "status" in result
    assert "incident_id" in result
    assert result["incident_id"] == "inc-1"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest projects/main-submission/tests/test_mcp_facade.py -v`
Expected: `FAIL` with ImportError.

- [ ] **Step 3: Implement MCP Facade**

Create `projects/main-submission/src/incident_copilot/mcp_facade.py`:

```python
import json
import hashlib
from dataclasses import asdict
from pathlib import Path
from fastmcp import FastMCP
from incident_copilot.rca_engine import build_rca
from incident_copilot.impact_scorer import score_assets

mcp = FastMCP("incident-copilot")


def get_rca_tool(test_case_id: str, signal_type: str = "unknown") -> dict:
    result = build_rca(
        failed_test={"message": signal_type, "testType": signal_type},
        entity_fqn=test_case_id,
        use_ai=False,
    )
    return {
        "cause_tree": result.cause_tree,
        "narrative": result.narrative,
        "narrative_source": result.narrative_source,
        "signal_type": result.signal_type,
    }


def _load_replay_context(
    path: str = "projects/main-submission/runtime/fixtures/replay_om_context.json",
) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _stable_hash(payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def score_impact_tool(entity_fqn: str, lineage_depth: int = 2) -> list[dict]:
    om_data = _load_replay_context()
    lineage = [
        item for item in (om_data.get("lineage") or [])
        if item.get("fqn") == entity_fqn and int(item.get("distance", 99)) <= lineage_depth
    ]
    return [asdict(item) for item in score_assets(lineage)]


def notify_slack_tool(incident_id: str) -> dict:
    payload = {"incident_id": incident_id}
    return {
        "status": "mirrored",
        "incident_id": incident_id,
        "fallback": "local_mirror",
        "mirror_path": "projects/main-submission/runtime/local_mirror/latest_brief.json",
        "payload_hash": _stable_hash(payload),
    }


@mcp.tool()
def triage_incident(incident_id: str, entity_fqn: str) -> dict:
    """Run full incident triage pipeline and return a 4-block brief."""
    from incident_copilot.orchestrator import run_pipeline
    raw_event = {
        "incident_id": incident_id,
        "entity_fqn": entity_fqn,
        "test_case_id": f"tc-{incident_id}",
        "severity": "high",
        "occurred_at": "",
        "raw_ref": incident_id,
    }
    om_data = _load_replay_context()
    result = run_pipeline(raw_event, om_data, slack_sender=lambda _: False)
    return {
        "brief": result["brief"],
        "delivery": result["delivery"],
        "mode": "replay_fixture",
    }


@mcp.tool()
def score_impact(entity_fqn: str, lineage_depth: int = 2) -> list[dict]:
    """Score impacted assets for a given entity FQN."""
    return score_impact_tool(entity_fqn, lineage_depth)


@mcp.tool()
def get_rca(test_case_id: str, signal_type: str = "unknown") -> dict:
    """Get root cause analysis for a failed test case."""
    return get_rca_tool(test_case_id, signal_type)


@mcp.tool()
def notify_slack(incident_id: str) -> dict:
    """Trigger Slack notification for an incident brief."""
    return notify_slack_tool(incident_id)


if __name__ == "__main__":
    mcp.run()
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest projects/main-submission/tests/test_mcp_facade.py -v`
Expected: all `PASS`.

- [ ] **Step 5: Commit**

```bash
git add projects/main-submission/src/incident_copilot/mcp_facade.py \
  projects/main-submission/tests/test_mcp_facade.py
git commit -m "feat: add MCP facade exposing triage_incident, score_impact, get_rca, notify_slack tools"
```

---

### Task 8: Full Suite Verification

**Files:**
- No new files. Runs all tests end-to-end.

- [ ] **Step 1: Install dependencies**

Run: `cd projects/main-submission && pip install -e ".[dev]"`

- [ ] **Step 2: Run full test suite without OpenRouter key**

```bash
cd projects/main-submission
python -m pytest tests/ -v
```

Expected: all tests `PASS`. All Claude paths fall back to templates since `OPENROUTER_API_KEY` is not set.

- [ ] **Step 3: Verify golden path still produces approval_required**

```bash
python -m pytest tests/test_orchestrator.py::test_golden_path_returns_approval_required -v
```

Expected: `PASS`.

- [ ] **Step 4: Verify demo harness determinism is preserved**

```bash
python -m pytest tests/test_demo_harness.py -v
```

Expected: all `PASS`.

- [ ] **Step 5: Run one-click demo twice and verify parity**

```bash
python scripts/run_demo.py --replay runtime/fixtures/replay_event.json \
  --context runtime/fixtures/replay_om_context.json \
  --output runtime/local_mirror/latest_brief.json

python scripts/run_demo.py --replay runtime/fixtures/replay_event.json \
  --context runtime/fixtures/replay_om_context.json \
  --output runtime/local_mirror/latest_brief.json
```

Expected: `runtime/local_mirror/latest_brief.json` is identical on both runs (deterministic, no key set).

- [ ] **Step 6: Verify direct HTTP vs `USE_OM_MCP=true` parity on replay fixture**

```bash
python scripts/run_demo.py --replay runtime/fixtures/replay_event.json \
  --context runtime/fixtures/replay_om_context.json \
  --output runtime/local_mirror/latest_http.json

USE_OM_MCP=true python scripts/run_demo.py --replay runtime/fixtures/replay_event.json \
  --context runtime/fixtures/replay_om_context.json \
  --output runtime/local_mirror/latest_mcp.json
```

Expected: canonical brief fields and policy state are identical between `latest_http.json` and `latest_mcp.json`.

- [ ] **Step 7: Verify Slack payload vs local mirror parity contract**

Run: `python -m pytest tests/test_delivery.py::test_slack_payload_matches_local_mirror_core_fields -v`
Expected: `PASS`; payload hashes or normalized core fields match exactly.

- [ ] **Step 8: Commit**

```bash
git add .
git commit -m "test: verify full suite and demo harness determinism after expanded pipeline"
```

---

## Critical Hardening Deltas (Required Before Build)

- [ ] Add `test_build_rca_falls_back_when_claude_returns_blank` and implement blank-response fallback to template in `rca_engine.py`.
- [ ] Add `test_claude_empty_list_falls_back_to_policy` and implement non-empty guard in `ai_recommender.py` before returning `source="claude"`.
- [ ] Add `test_distance_zero_is_clamped` and clamp `distance` to `>=1` in `impact_scorer.py` to prevent divide-by-zero.
- [ ] Replace MCP facade stubs:
Use replay fixture-backed context loading for `triage_incident` instead of inline empty `om_data` dict.
- [ ] Add an explicit parity test:
`test_mcp_facade.py::test_triage_incident_parity_with_run_pipeline_replay_fixture`.
- [ ] Add deterministic one-click entrypoint docs:
`scripts/run_demo.py` must document where `om_data` fixture comes from and expected output files.
- [ ] Ensure `notify_slack_tool` hashes canonical brief payload (not just `incident_id`) so parity checks are meaningful.
- [ ] Add explicit implementation task for `context_resolver.py`:
support `USE_OM_MCP=true` by calling OM MCP tools first, then fallback to direct HTTP when MCP errors or times out.
- [ ] Add resolver mode tests in `test_context_resolver.py`:
direct mode and MCP mode must return equivalent normalized context on replay fixtures.

## End-to-End Verification Checklist

- [ ] `test_rca_engine.py` — all signal types map to correct cause tree, template fallback always non-empty.
- [ ] `test_rca_engine.py` — Claude called when key available, template used when Claude raises.
- [ ] `test_rca_engine.py` — blank Claude response falls back to template narrative.
- [ ] `test_impact_scorer.py` — formula correct, score_reason contains all terms, sorted descending.
- [ ] `test_impact_scorer.py` — distance `0` or missing values are clamped safely to `1`.
- [ ] `test_ai_recommender.py` — policy fallback when no key or no asset, Claude used when available.
- [ ] `test_ai_recommender.py` — `approval_required` fallback mentions steward.
- [ ] `test_ai_recommender.py` — blank Claude output falls back to deterministic policy bullets.
- [ ] `test_orchestrator.py` — `rca`, `scored_assets`, `recommendation` in output.
- [ ] `test_orchestrator.py` — `what_failed` text contains RCA narrative.
- [ ] `test_orchestrator.py` — `what_is_impacted` text contains `score:`.
- [ ] `test_context_resolver.py` — `USE_OM_MCP=true` and direct mode produce equivalent normalized context on replay fixtures.
- [ ] `test_context_resolver.py` — MCP resolver failures/timeouts fallback to direct HTTP with non-empty fallback reason codes.
- [ ] `test_mcp_facade.py` — all 4 MCP tools callable as plain functions.
- [ ] `test_mcp_facade.py` — `triage_incident` replay-fixture output matches direct `run_pipeline` output.
- [ ] `test_mcp_facade.py` — `notify_slack` payload hash is derived from canonical brief payload.
- [ ] `test_delivery.py` — Slack payload and local mirror persisted core fields are identical.
- [ ] Full suite passes with no `OPENROUTER_API_KEY` set.
- [ ] Demo harness produces identical output on two consecutive runs.
- [ ] Direct HTTP mode and `USE_OM_MCP=true` mode produce identical brief outputs on the same replay fixture.
