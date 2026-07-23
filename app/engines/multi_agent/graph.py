"""Sequential multi_agent pipeline (no HITL interrupt yet)."""

from __future__ import annotations

from app.engines.multi_agent.nodes_analyst import node_analyst
from app.engines.multi_agent.nodes_reviewer import node_reviewer
from app.engines.multi_agent.nodes_router import node_router
from app.engines.multi_agent.nodes_search import node_search
from app.engines.multi_agent.nodes_synthesize import node_synthesize
from app.engines.multi_agent.state import AgentState


def run_pipeline(initial: AgentState) -> AgentState:
    state = node_router(initial)
    route = state.get("route") or "both"

    if route in ("web", "both"):
        state = node_search(state)
    if route in ("data", "both"):
        state = node_analyst(state)

    state = node_reviewer(state)
    state = node_synthesize(state)
    return state
