from incident_copilot.adapter import normalize_event
from incident_copilot.context_resolver import resolve_context
from incident_copilot.owner_routing import resolve_first_responder
from incident_copilot.impact import select_top_impacted_assets
from incident_copilot.impact_scorer import score_assets
from incident_copilot.rca_engine import build_rca
from incident_copilot.policy import evaluate_policy
from incident_copilot.ai_recommender import recommend
from incident_copilot.brief import build_incident_brief
from incident_copilot.delivery import deliver

_DEFAULT_MIRROR = "projects/main-submission/runtime/local_mirror/latest_brief.json"


def run_pipeline(raw_event, om_data, slack_sender, mirror_writer=lambda _payload: _DEFAULT_MIRROR):
    env = normalize_event(raw_event)
    ctx = resolve_context(env, om_data, max_depth=2)

    impacted = select_top_impacted_assets(ctx["impacted_assets"], max_assets=3, max_depth=2)
    scored = score_assets(impacted)
    rca = build_rca(ctx["failed_test"], env.get("entity_fqn", ""), use_ai=True)
    policy = evaluate_policy(env["incident_id"], impacted)
    top_asset = scored[0] if scored else None
    recommendation = recommend(ctx["failed_test"], top_asset, policy)

    first_actor, first_path = resolve_first_responder(
        ctx["owners"].get("asset_owner"),
        ctx["owners"].get("domain_owner"),
        ctx["owners"].get("team_owner"),
        "#metadata-incidents",
    )

    brief = build_incident_brief(
        incident_id=env["incident_id"],
        what_failed=(
            rca.narrative,
            ["incident_ref", "test_ref", f"rca:{rca.signal_type}"],
        ),
        what_is_impacted=(
            ", ".join(f"{a.fqn} (score:{a.score})" for a in scored) or "none",
            ["lineage_ref"] + [f"score:{a.fqn}" for a in scored],
        ),
        who_acts_first=(f"{first_actor} via {first_path}", ["owner_ref"]),
        what_to_do_next=(
            "\n".join(f"• {b}" for b in recommendation.bullets),
            ["policy_ref", "classification_ref"]
            if policy.status == "approval_required"
            else ["policy_ref"],
        ),
        policy_state=policy.status,
    )

    delivery_result = deliver(brief, slack_sender, mirror_writer)

    return {
        "brief": brief,
        "delivery": delivery_result,
        "rca": rca,
        "scored_assets": scored,
        "recommendation": recommendation,
        "fallback_reason_codes": (
            env["fallback_reason_codes"]
            + ctx["fallback_reason_codes"]
            + (delivery_result["delivery"].degraded_reason_codes or [])
        ),
    }
