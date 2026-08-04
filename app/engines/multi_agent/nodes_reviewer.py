"""Reviewer node: rules-only sufficiency check."""

from __future__ import annotations

from app.engines.multi_agent.state import AgentState
from app.engines.multi_agent.text_sanitize import sanitize_snippet


def node_reviewer(state: AgentState) -> AgentState:
    route = state.get("route") or "both"
    citations = state.get("citations") or []
    risks = list(state.get("risks") or [])

    types = {c.get("type") for c in citations}
    ok = True

    if state.get("force_reviewer_insufficient"):
        risks.append("forced insufficiency (force_reviewer_insufficient=true)")
        ok = False
    else:
        if (
            route in ("web", "both")
            and "web" not in types
            and "no_hit" not in types
        ):
            risks.append("missing web citations for web/both route")
            ok = False
        if (
            route in ("data", "both")
            and "data" not in types
            and "no_hit" not in types
        ):
            risks.append("missing data citations for data/both route")
            ok = False

    web_lines = []
    for c in citations:
        if c.get("type") != "web":
            continue
        title = sanitize_snippet(c.get("title") or "", max_len=80) or "(untitled)"
        snip = sanitize_snippet(c.get("snippet") or "", max_len=80)
        if snip and snip != "(encoding unclear)":
            web_lines.append("- {0}: {1}".format(title, snip))
        else:
            web_lines.append("- {0}".format(title))

    data_line = state.get("data_summary") or "no data summary"
    draft_parts = [
        "### Data",
        data_line,
        "",
        "### Route",
        str(route),
        "",
        "### Web (short)",
        "\n".join(web_lines) if web_lines else "(none)",
        "",
        "### Review",
        "ok: {0}".format(ok),
    ]
    if state.get("last_feedback"):
        draft_parts.extend(
            [
                "",
                "### Last revise feedback",
                str(state.get("last_feedback")),
            ]
        )
        tgt = state.get("last_revise_target")
        if tgt:
            draft_parts.append("target: {0}".format(tgt))
    if risks:
        draft_parts.extend(["", "### Risks", "; ".join(risks)])

    state["draft"] = "\n".join(draft_parts)
    state["risks"] = risks
    state["ok"] = ok
    return state
