def resolve_first_responder(asset_owner, domain_owner, team_owner, default_channel):
    if asset_owner:
        return asset_owner, "asset_owner"
    if domain_owner:
        return domain_owner, "domain_owner"
    if team_owner:
        return team_owner, "team_owner"
    return default_channel, "default_channel"
