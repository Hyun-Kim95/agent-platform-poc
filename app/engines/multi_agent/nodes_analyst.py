"""Analyst node: CSV revenue sum."""

from __future__ import annotations

from app.engines.multi_agent.state import AgentState
from app.engines.multi_agent.tools_analyst import sum_revenue


def node_analyst(state: AgentState) -> AgentState:
    data_path = state.get("data_path") or "samples/mini.csv"
    total, summary = sum_revenue(data_path)
    state["data_summary"] = summary
    state["data_value"] = total
    citations = list(state.get("citations") or [])
    risks = list(state.get("risks") or [])

    if total is None:
        citations.append(
            {
                "type": "no_hit",
                "ref": "",
                "title": "data analysis failed",
                "snippet": summary,
            }
        )
        risks.append(summary)
        state["ok"] = False
    else:
        citations.append(
            {
                "type": "data",
                "ref": "{0}#revenue_sum".format(data_path.replace("\\", "/")),
                "title": "revenue sum",
                "snippet": str(total),
            }
        )

    state["citations"] = citations
    state["risks"] = risks
    return state
