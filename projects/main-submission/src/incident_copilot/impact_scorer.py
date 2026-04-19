import math

from incident_copilot.contracts import ScoredAsset


def _coerce_distance(distance: object) -> int:
    try:
        normalized = int(distance)
    except (TypeError, ValueError):
        return 1
    return max(1, normalized)


def score_asset(asset: dict) -> ScoredAsset:
    business_facing = bool(asset.get("business_facing", False))
    pii_sensitive = "PII.Sensitive" in (asset.get("classifications") or [])
    distance = _coerce_distance(asset.get("distance", 1))
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
