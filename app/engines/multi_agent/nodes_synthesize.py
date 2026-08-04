"""Synthesize final answer from draft + citations."""

from __future__ import annotations

from app.engines.multi_agent.state import AgentState
from app.engines.multi_agent.text_sanitize import sanitize_snippet


def node_synthesize(state: AgentState) -> AgentState:
    route = state.get("route") or "both"
    lines = []
    lines.append("## Answer")
    lines.append("")

    if route in ("data", "both"):
        lines.append("### Data (CSV)")
        val = state.get("data_value")
        if val is None:
            lines.append(state.get("data_summary") or "Data unavailable.")
        else:
            lines.append(
                "Revenue sum from CSV: {0} ({1})".format(
                    val, state.get("data_summary") or ""
                )
            )
        lines.append("")

    if route in ("web", "both"):
        lines.append("### Public web summary")
        hits = state.get("web_hits") or []
        if not hits:
            lines.append("No web hits (see citations).")
        else:
            for h in hits:
                title = sanitize_snippet(h.get("title") or "untitled", 80)
                url = h.get("url") or ""
                lines.append("- {0} ({1})".format(title, url))
                snip = sanitize_snippet(h.get("snippet") or "", 100)
                if snip and snip != "(encoding unclear)":
                    lines.append("  {0}".format(snip))

    risks = state.get("risks") or []
    if risks:
        lines.append("")
        lines.append("### Notes")
        for r in risks:
            lines.append("- {0}".format(r))

    fb = state.get("last_feedback")
    if fb:
        lines.append("")
        lines.append("### Last revise feedback")
        lines.append(str(fb))

    state["answer"] = "\n".join(lines).strip()
    return state
