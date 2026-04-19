from incident_copilot.owner_routing import resolve_first_responder


def test_asset_owner_priority():
    assert resolve_first_responder("a", "d", "t", "#x") == ("a", "asset_owner")


def test_domain_owner_fallback():
    assert resolve_first_responder(None, "d", "t", "#x") == ("d", "domain_owner")


def test_team_owner_fallback():
    assert resolve_first_responder(None, None, "t", "#x") == ("t", "team_owner")


def test_default_channel_fallback():
    assert resolve_first_responder(None, None, None, "#x") == ("#x", "default_channel")
