from incident_copilot.impact import select_top_impacted_assets


def test_business_facing_assets_rank_first():
    assets = [
        {"fqn": "a.raw", "distance": 1, "business_facing": False},
        {"fqn": "a.dashboard", "distance": 2, "business_facing": True},
    ]
    out = select_top_impacted_assets(assets, max_assets=3, max_depth=2)
    assert out[0]["fqn"] == "a.dashboard"


def test_caps_to_three_and_depth_two():
    assets = [{"fqn": f"a{i}", "distance": 1, "business_facing": True} for i in range(5)]
    out = select_top_impacted_assets(assets, max_assets=3, max_depth=2)
    assert len(out) == 3
