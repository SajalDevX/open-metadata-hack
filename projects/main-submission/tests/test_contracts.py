from incident_copilot.contracts import BriefBlock, PolicyDecision, DeliveryResult


def test_brief_block_requires_evidence_refs():
    block = BriefBlock(text="what failed", evidence_refs=["incident_ref", "test_ref"])
    assert block.evidence_refs == ["incident_ref", "test_ref"]


def test_policy_decision_has_reason_codes_and_approver():
    item = PolicyDecision(
        incident_id="inc-1",
        status="approval_required",
        reason_codes=["PII_SENSITIVE_IMPACTED"],
        required_approver_role="data_steward",
    )
    assert item.required_approver_role == "data_steward"


def test_delivery_result_tracks_primary_output():
    out = DeliveryResult(slack_status="failed", local_status="rendered", primary_output="local_mirror")
    assert out.primary_output == "local_mirror"


def test_rca_result_fields():
    from incident_copilot.contracts import RCAResult
    r = RCAResult(
        cause_tree=["data_completeness", "upstream_null_propagation"],
        narrative="Null ratio exceeded threshold.",
        narrative_source="template",
        signal_type="null_ratio_exceeded",
    )
    assert r.cause_tree[0] == "data_completeness"
    assert r.narrative_source == "template"


def test_scored_asset_fields():
    from incident_copilot.contracts import ScoredAsset
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
    from incident_copilot.contracts import RecommendationResult
    r = RecommendationResult(bullets=["Check upstream", "Notify owner"], source="claude")
    assert len(r.bullets) == 2
    assert r.source == "claude"
