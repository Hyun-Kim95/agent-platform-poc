"""LangGraph multi_agent pipeline with interrupt HITL + reviewer loop."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Literal, Optional

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.engines.multi_agent.nodes_analyst import node_analyst
from app.engines.multi_agent.nodes_reviewer import node_reviewer
from app.engines.multi_agent.nodes_router import node_router
from app.engines.multi_agent.nodes_search import node_search
from app.engines.multi_agent.nodes_synthesize import node_synthesize
from app.engines.multi_agent.state import AgentState

_COMPILED = None


def _archive_and_clear_evidence(
    state: AgentState, *, round_id: int
) -> AgentState:
    """Keep current citations in citation_history, then clear live evidence."""
    state = dict(state)
    cites = list(state.get("citations") or [])
    history = list(state.get("citation_history") or [])
    if cites:
        history.append(
            {
                "round": round_id,
                "citations": cites,
            }
        )
        risks = list(state.get("risks") or [])
        risks.append(
            "archived {0} citation(s) from round {1}".format(
                len(cites), round_id
            )
        )
        state["risks"] = risks
    state["citation_history"] = history
    state["citations"] = []
    state["web_hits"] = []
    state["data_summary"] = ""
    state["data_value"] = None
    state["draft"] = ""
    return state


def _tools_node(state: AgentState) -> AgentState:
    route = state.get("route") or "both"
    target = state.get("revise_target")
    if target is None:
        if route in ("web", "both"):
            state = node_search(state)
        if route in ("data", "both"):
            state = node_analyst(state)
    elif target == "search":
        state = node_search(state)
    elif target == "analyst":
        state = node_analyst(state)
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


def _route_after_review(
    state: AgentState,
) -> Literal["human", "loop_gate"]:
    if state.get("ok", True):
        return "human"
    return "loop_gate"


def _loop_gate_node(state: AgentState) -> Any:
    """Count a failed review; retry tools or end with MAX_ITERATIONS."""
    state = dict(state)
    it = int(state.get("iteration") or 0) + 1
    state["iteration"] = it
    max_it = int(state.get("max_iterations") or 8)
    risks = list(state.get("risks") or [])
    risks.append("reviewer loop iteration={0}/{1}".format(it, max_it))
    state["risks"] = risks

    if it >= max_it:
        state["error_code"] = "MAX_ITERATIONS"
        state["ok"] = False
        state["answer"] = ""
        return Command(goto=END, update=state)

    state = _archive_and_clear_evidence(state, round_id=it)
    state["ok"] = True
    state["error_code"] = None
    return Command(goto="tools", update=state)


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

    # W2.5 H5: keep feedback in risks/hitl only — do not pollute web search query.

    state["risks"] = risks
    state["citations"] = citations
    state["revise_target"] = target
    state["last_feedback"] = feedback or None
    state["last_revise_target"] = target
    state["answer"] = ""
    state["iteration"] = 0
    state["error_code"] = None
    state["ok"] = True
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

    return Command(goto="synthesize")


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("router", _router_node)
    g.add_node("tools", _tools_node)
    g.add_node("reviewer", _reviewer_node)
    g.add_node("loop_gate", _loop_gate_node)
    g.add_node("human", _human_node)
    g.add_node("synthesize", _synthesize_node)

    g.add_edge(START, "router")
    g.add_edge("router", "tools")
    g.add_edge("tools", "reviewer")
    g.add_conditional_edges(
        "reviewer",
        _route_after_review,
        {
            "human": "human",
            "loop_gate": "loop_gate",
        },
    )
    g.add_edge("synthesize", END)
    return g


def get_compiled_graph():
    global _COMPILED
    if _COMPILED is None:
        from app.engines.multi_agent.checkpoint import get_checkpointer

        _COMPILED = build_graph().compile(checkpointer=get_checkpointer())
    return _COMPILED


def reset_compiled_graph() -> None:
    """Drop the process-local compiled graph cache.

    Dev/test helper only. Normal API traffic never calls this; restarting
    uvicorn already reloads the module. Use in REPL/unit tests after editing
    graph code in the same Python process.
    """
    global _COMPILED
    _COMPILED = None


def thread_config(run_id: str) -> Dict[str, Any]:
    return {"configurable": {"thread_id": run_id}}


def finalize_answer(state: AgentState) -> AgentState:
    return node_synthesize(dict(state))


def revise_pipeline(
    state: AgentState,
    revise_target: Optional[str],
    feedback: str,
) -> AgentState:
    updated = build_revise_updates(state, feedback, revise_target)
    max_it = int(updated.get("max_iterations") or 8)
    while True:
        updated = _tools_node(updated)
        updated = _reviewer_node(updated)
        if updated.get("ok", True):
            return updated
        it = int(updated.get("iteration") or 0) + 1
        updated["iteration"] = it
        risks = list(updated.get("risks") or [])
        risks.append("reviewer loop iteration={0}/{1}".format(it, max_it))
        updated["risks"] = risks
        if it >= max_it:
            updated["error_code"] = "MAX_ITERATIONS"
            updated["ok"] = False
            updated["answer"] = ""
            return updated
        updated = _archive_and_clear_evidence(updated, round_id=it)
        updated["ok"] = True
        updated["error_code"] = None


def run_pipeline(initial: AgentState) -> AgentState:
    graph = get_compiled_graph()
    cfg = thread_config("pipe_{0}".format(uuid.uuid4().hex))
    initial = dict(initial)
    initial["hitl_enabled"] = False
    return dict(graph.invoke(initial, cfg))
