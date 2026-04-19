def _block(text, refs):
    return {"text": text, "evidence_refs": refs}


def build_incident_brief(
    incident_id,
    what_failed,
    what_is_impacted,
    who_acts_first,
    what_to_do_next,
    policy_state,
):
    wf_text, wf_refs = what_failed
    wi_text, wi_refs = what_is_impacted
    wa_text, wa_refs = who_acts_first
    wn_text, wn_refs = what_to_do_next
    return {
        "incident_id": incident_id,
        "what_failed": _block(wf_text, wf_refs),
        "what_is_impacted": _block(wi_text, wi_refs),
        "who_acts_first": _block(wa_text, wa_refs),
        "what_to_do_next": _block(wn_text, wn_refs),
        "policy_state": policy_state,
    }
