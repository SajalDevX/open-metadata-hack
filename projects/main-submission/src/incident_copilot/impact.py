def _sort_key(item):
    return (
        0 if item.get("business_facing") else 1,
        item.get("distance", 99),
        item.get("fqn", ""),
    )


def select_top_impacted_assets(assets, max_assets=3, max_depth=2):
    bounded = [x for x in assets if x.get("distance", 99) <= max_depth]
    return sorted(bounded, key=_sort_key)[:max_assets]
