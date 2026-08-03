"""Search node: collect web citations."""

from __future__ import annotations

from app.engines.multi_agent.state import AgentState
from app.engines.multi_agent.tools_search import search_web


def node_search(state: AgentState) -> AgentState:
    hits, source, mock_reason = search_web(
        state.get("query") or "", max_results=3
    )
    state["web_hits"] = hits
    state["web_search_source"] = source
    citations = list(state.get("citations") or [])
    risks = list(state.get("risks") or [])
    risks.append(
        "web_search_source={0}{1}".format(
            source,
            (" reason=" + mock_reason) if mock_reason else "",
        )
    )
    state["risks"] = risks

    if not hits:
        citations.append(
            {
                "type": "no_hit",
                "ref": "",
                "title": "web search returned no results",
                "snippet": None,
            }
        )
    else:
        for h in hits:
            citations.append(
                {
                    "type": "web",
                    "ref": h.get("url") or "",
                    "title": h.get("title") or "",
                    "snippet": h.get("snippet"),
                }
            )

    state["citations"] = citations
    return state
