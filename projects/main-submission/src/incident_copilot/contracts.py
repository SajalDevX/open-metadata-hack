from dataclasses import dataclass


@dataclass(frozen=True)
class BriefBlock:
    text: str
    evidence_refs: list[str]


@dataclass(frozen=True)
class PolicyDecision:
    incident_id: str
    status: str  # allowed | approval_required
    reason_codes: list[str]
    required_approver_role: str | None


@dataclass(frozen=True)
class DeliveryResult:
    slack_status: str
    local_status: str
    primary_output: str  # slack | local_mirror
    degraded_reason_codes: list[str] | None = None


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
