"""Sequential multi_agent pipeline with HITL pause points."""

from __future__ import annotations

from typing import Optional

from app.engines.multi_agent.nodes_analyst import node_analyst
from app.engines.multi_agent.nodes_reviewer import node_reviewer
from app.engines.multi_agent.nodes_router import node_router
from app.engines.multi_agent.nodes_search import node_search
from app.engines.multi_agent.nodes_synthesize import node_synthesize
from app.engines.multi_agent.state import AgentState


def run_until_review(initial: AgentState) -> AgentState:
    """Router -> tools -> reviewer (no synthesize)."""
    state = node_router(initial)
    route = state.get("route") or "both"
    if route in ("web", "both"):
        state = node_search(state)
    if route in ("data", "both"):
        state = node_analyst(state)
    state = node_reviewer(state)
    return state


def finalize_answer(state: AgentState) -> AgentState:
    return node_synthesize(state)


def revise_pipeline(
    state: AgentState,
    revise_target: Optional[str],
    feedback: str,
) -> AgentState:
    """Re-run search and/or analyst, then reviewer. Keeps query/route."""
    risks = list(state.get("risks") or [])
    risks.append("human revise: {0}".format(feedback))
    state["risks"] = risks

    citations = list(state.get("citations") or [])
    target = revise_target  # None => both
    if target is None or target == "search":
        citations = [c for c in citations if c.get("type") != "web"]
        state["web_hits"] = []
    if target is None or target == "analyst":
        citations = [c for c in citations if c.get("type") != "data"]
        state["data_summary"] = ""
        state["data_value"] = None
    citations = [c for c in citations if c.get("type") != "no_hit"]
    state["citations"] = citations

    route = state.get("route") or "both"
    if target is None:
        if route in ("web", "both"):
            state = node_search(state)
        if route in ("data", "both"):
            state = node_analyst(state)
    elif target == "search":
        state = node_search(state)
    elif target == "analyst":
        state = node_analyst(state)

    state = node_reviewer(state)
    return state


def run_pipeline(initial: AgentState) -> AgentState:
    """Full path without HITL (hitl off tenants)."""
    state = run_until_review(initial)
    return finalize_answer(state)
