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
            bullets = [bullet for bullet in _claude_recommend(failed_test, top_asset, policy) if bullet.strip()]
            if bullets:
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
