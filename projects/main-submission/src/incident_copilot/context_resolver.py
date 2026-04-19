def resolve_context(envelope, om_client_data, max_depth=2):
    owners = om_client_data.get("owners", {})
    fallback_reason_codes = []
    if not owners.get("asset_owner") and not owners.get("domain_owner") and not owners.get("team_owner"):
        fallback_reason_codes.append("MISSING_OWNER_METADATA")
    classifications_map = om_client_data.get("classifications", {})
    impacted = []
    for item in om_client_data.get("lineage", []):
        if item.get("distance", 99) > max_depth:
            continue
        merged = dict(item)
        merged["classifications"] = merged.get("classifications") or classifications_map.get(merged.get("fqn"), [])
        impacted.append(merged)
    return {
        "incident_id": envelope["incident_id"],
        "failed_test": om_client_data.get("failed_test", {}),
        "impacted_assets": impacted,
        "owners": owners,
        "classifications": classifications_map,
        "fallback_reason_codes": fallback_reason_codes,
    }
