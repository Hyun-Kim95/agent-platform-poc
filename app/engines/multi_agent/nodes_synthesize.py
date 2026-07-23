"""Synthesize final answer from draft + citations."""

from __future__ import annotations

from app.engines.multi_agent.state import AgentState


def node_synthesize(state: AgentState) -> AgentState:
    route = state.get("route") or "both"
    lines = []
    lines.append("## Answer")
    lines.append("")

    if route in ("web", "both"):
        lines.append("### Public web summary")
        hits = state.get("web_hits") or []
        if not hits:
            lines.append("No web hits (see citations).")
        else:
            for h in hits:
                lines.append(
                    "- {0} ({1})".format(
                        h.get("title") or "untitled", h.get("url") or ""
                    )
                )
                if h.get("snippet"):
                    lines.append("  {0}".format(h["snippet"][:240]))

    if route in ("data", "both"):
        lines.append("")
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

    risks = state.get("risks") or []
    if risks:
        lines.append("")
        lines.append("### Notes")
        for r in risks:
            lines.append("- {0}".format(r))

    state["answer"] = "\n".join(lines).strip()
    return state
