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


def test_distance_zero_is_clamped():
    asset = {"fqn": "a", "business_facing": False, "distance": 0, "downstream_count": 0, "classifications": []}
    result = score_asset(asset)
    assert result.distance == 1
    assert "distance=1" in result.score_reason


def test_missing_distance_defaults_to_one():
    asset = {"fqn": "a", "business_facing": False, "downstream_count": 0, "classifications": []}
    result = score_asset(asset)
    assert result.distance == 1
    assert "distance=1" in result.score_reason
