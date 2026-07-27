"""LangGraph multi_agent pipeline with interrupt HITL."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.engines.multi_agent.nodes_analyst import node_analyst
from app.engines.multi_agent.nodes_reviewer import node_reviewer
from app.engines.multi_agent.nodes_router import node_router
from app.engines.multi_agent.nodes_search import node_search
from app.engines.multi_agent.nodes_synthesize import node_synthesize
from app.engines.multi_agent.state import AgentState

# Process-local checkpointer (warm resume). Cold resume uses SQLite agent_state.
_CHECKPOINTER = MemorySaver()
_COMPILED = None


def _tools_node(state: AgentState) -> AgentState:
    route = state.get("route") or "both"
    target = state.get("revise_target")  # None => follow route
    if target is None:
        if route in ("web", "both"):
            state = node_search(state)
        if route in ("data", "both"):
            state = node_analyst(state)
    elif target == "search":
        state = node_search(state)
    elif target == "analyst":
        state = node_analyst(state)
    # one-shot revise targeting
    if "revise_target" in state:
        state = dict(state)
        state["revise_target"] = None
    return state


def _reviewer_node(state: AgentState) -> AgentState:
    return node_reviewer(state)


def _router_node(state: AgentState) -> AgentState:
    return node_router(state)


def _synthesize_node(state: AgentState) -> AgentState:
    return node_synthesize(state)


def build_revise_updates(
    state: AgentState,
    feedback: str,
    revise_target: Optional[str],
) -> Dict[str, Any]:
    """Clear evidence for re-run; used by human node and cold-resume fallback."""
    state = dict(state)
    risks = list(state.get("risks") or [])
    risks.append("human revise: {0}".format(feedback))

    citations = list(state.get("citations") or [])
    target = revise_target
    route = state.get("route") or "both"

    if target == "search" and route == "data":
        risks.append("revise_target=search ignored (route=data)")
        target = "analyst"
    elif target == "analyst" and route == "web":
        risks.append("revise_target=analyst ignored (route=web)")
        target = "search"

    if target is None or target == "search":
        citations = [c for c in citations if c.get("type") != "web"]
        state["web_hits"] = []
    if target is None or target == "analyst":
        citations = [c for c in citations if c.get("type") != "data"]
        state["data_summary"] = ""
        state["data_value"] = None
    citations = [c for c in citations if c.get("type") != "no_hit"]

    if feedback and (target is None or target == "search"):
        base_q = state.get("query") or ""
        state["query"] = "{0}\n(human revise: {1})".format(base_q, feedback)

    state["risks"] = risks
    state["citations"] = citations
    state["revise_target"] = target
    state["answer"] = ""
    return state


def _human_node(state: AgentState) -> Any:
    if not state.get("hitl_enabled"):
        return Command(goto="synthesize")

    payload = interrupt(
        {
            "draft": state.get("draft") or "",
            "risks": list(state.get("risks") or []),
        }
    )
    if not isinstance(payload, dict):
        payload = {"decision": "approve"}

    decision = payload.get("decision") or "approve"
    if decision == "reject":
        return Command(
            goto=END,
            update={
                "answer": "Rejected by human.",
                "ok": False,
            },
        )
    if decision == "revise":
        updated = build_revise_updates(
            state,
            feedback=(payload.get("feedback") or ""),
            revise_target=payload.get("revise_target"),
        )
        return Command(goto="tools", update=updated)

    # approve
    return Command(goto="synthesize")


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("router", _router_node)
    g.add_node("tools", _tools_node)
    g.add_node("reviewer", _reviewer_node)
    g.add_node("human", _human_node)
    g.add_node("synthesize", _synthesize_node)

    g.add_edge(START, "router")
    g.add_edge("router", "tools")
    g.add_edge("tools", "reviewer")
    g.add_edge("reviewer", "human")
    g.add_edge("synthesize", END)
    return g


def get_compiled_graph():
    global _COMPILED
    if _COMPILED is None:
        _COMPILED = build_graph().compile(checkpointer=_CHECKPOINTER)
    return _COMPILED


def thread_config(run_id: str) -> Dict[str, Any]:
    return {"configurable": {"thread_id": run_id}}


# --- Cold-resume helpers (server reload: MemorySaver empty) ---


def finalize_answer(state: AgentState) -> AgentState:
    return node_synthesize(dict(state))


def revise_pipeline(
    state: AgentState,
    revise_target: Optional[str],
    feedback: str,
) -> AgentState:
    updated = build_revise_updates(state, feedback, revise_target)
    updated = _tools_node(updated)
    updated = _reviewer_node(updated)
    return updated


def run_pipeline(initial: AgentState) -> AgentState:
    """hitl off convenience (also covered by graph path)."""
    graph = get_compiled_graph()
    cfg = thread_config("pipe_{0}".format(uuid.uuid4().hex))
    initial = dict(initial)
    initial["hitl_enabled"] = False
    return dict(graph.invoke(initial, cfg))
