"""Reviewer node: rules-only sufficiency check (+ optional loop force)."""

from __future__ import annotations

from app.engines.multi_agent.state import AgentState

# Query substring for loop smoke only (not a production signal).
FORCE_INSUFFICIENT_MARK = "FORCE_INSUFFICIENT"


def node_reviewer(state: AgentState) -> AgentState:
    route = state.get("route") or "both"
    citations = state.get("citations") or []
    risks = list(state.get("risks") or [])
    query = state.get("query") or ""

    types = {c.get("type") for c in citations}
    ok = True

    if FORCE_INSUFFICIENT_MARK in query:
        risks.append("forced insufficiency for reviewer loop test")
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

    web_bits = []
    for c in citations:
        if c.get("type") == "web":
            web_bits.append(
                "- {0}: {1}".format(
                    c.get("title") or "", (c.get("snippet") or "")[:160]
                )
            )

    data_line = state.get("data_summary") or "no data summary"
    draft_parts = [
        "Route: {0}".format(route),
        "Web notes:",
        "\n".join(web_bits) if web_bits else "(none)",
        "Data: {0}".format(data_line),
        "Review ok: {0}".format(ok),
    ]
    if risks:
        draft_parts.append("Risks: {0}".format("; ".join(risks)))

    state["draft"] = "\n".join(draft_parts)
    state["risks"] = risks
    state["ok"] = ok
    return state
