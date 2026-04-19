"""ANSI terminal renderer for an incident brief — for CLI / terminal-based demos."""

_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_DIM = "\x1b[2m"
_RED_BG = "\x1b[41;97m"
_GREEN_BG = "\x1b[42;30m"
_BLUE = "\x1b[34m"
_YELLOW = "\x1b[33m"
_CYAN = "\x1b[36m"
_MAGENTA = "\x1b[35m"


def _c(code: str, text: str, use_color: bool) -> str:
    return f"{code}{text}{_RESET}" if use_color else text


def _badge(policy: str, use_color: bool) -> str:
    if policy == "approval_required":
        return _c(_RED_BG, f" {policy.upper()} ", use_color)
    return _c(_GREEN_BG, f" {policy.upper()} ", use_color)


def _tag_color(ref: str) -> str:
    if ref.startswith("rca:"):
        return _BLUE
    if ref.startswith("score:"):
        return _YELLOW
    return _CYAN


def _render_block(label: str, block: dict, use_color: bool) -> str:
    if not isinstance(block, dict):
        block = {}
    text = str(block.get("text", "")).strip()
    refs = block.get("evidence_refs") or []

    header = _c(_BOLD + _MAGENTA, label, use_color)
    lines = [header]
    for text_line in text.splitlines() or [""]:
        lines.append(f"  {text_line}")
    if refs:
        tags = "  ".join(_c(_tag_color(r), r, use_color) for r in refs)
        lines.append("  " + _c(_DIM, f"[{tags}]", use_color))
    return "\n".join(lines)


def render_brief_terminal(brief: dict, use_color: bool = True) -> str:
    incident_id = str(brief.get("incident_id", "unknown"))
    policy = str(brief.get("policy_state", "allowed"))

    top = _c(_BOLD, f"Incident {incident_id}", use_color) + "   " + _badge(policy, use_color)
    divider = _c(_DIM, "─" * 70, use_color)

    blocks = [
        _render_block("WHAT FAILED", brief.get("what_failed", {}), use_color),
        _render_block("WHAT IS IMPACTED", brief.get("what_is_impacted", {}), use_color),
        _render_block("WHO ACTS FIRST", brief.get("who_acts_first", {}), use_color),
        _render_block("WHAT TO DO NEXT", brief.get("what_to_do_next", {}), use_color),
    ]

    return "\n".join([top, divider, "", *["\n".join([b, ""]) for b in blocks]])
