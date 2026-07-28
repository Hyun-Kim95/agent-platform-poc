"""multi_agent engine backed by LangGraph (+ cold-resume fallback)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from langgraph.types import Command

from app.core.models import (
    Citation,
    Envelope,
    EngineContext,
    ErrorObject,
    HitlPreview,
    HitlView,
    Meta,
    RunStatus,
)
from app.engines.multi_agent.graph import (
    finalize_answer,
    get_compiled_graph,
    revise_pipeline,
    thread_config,
)
from app.engines.multi_agent.state import AgentState

RunResult = Tuple[Envelope, Dict[str, Any]]


class MultiAgentEngine:
    name = "multi_agent"

    def run(self, ctx: EngineContext) -> RunResult:
        initial: AgentState = {
            "query": ctx.query,
            "data_path": ctx.data_path,
            "rules_only": ctx.rules_only,
            "hitl_enabled": ctx.hitl_enabled,
            "force_reviewer_insufficient": ctx.force_reviewer_insufficient,
            "max_iterations": ctx.max_iterations,
            "iteration": 0,
            "error_code": None,
            "citations": [],
            "citation_history": [],
            "risks": [],
            "ok": True,
        }
        graph = get_compiled_graph()
        cfg = thread_config(ctx.run_id)
        graph.invoke(initial, cfg)
        snap = graph.get_state(cfg)
        values = dict(snap.values or {})

        if snap.next:
            return self._waiting_envelope(ctx, values), values

        if values.get("error_code") == "MAX_ITERATIONS":
            return (
                self._failed_envelope(
                    ctx,
                    values,
                    code="MAX_ITERATIONS",
                    message=(
                        "reviewer loop exceeded max_iterations={0}".format(
                            ctx.max_iterations
                        )
                    ),
                ),
                values,
            )

        return (
            self._to_envelope(ctx, values, RunStatus.completed, hitl=None),
            values,
        )

    def resume(
        self,
        ctx: EngineContext,
        agent_state: AgentState,
        decision: str,
        feedback: Optional[str] = None,
        revise_target: Optional[str] = None,
    ) -> RunResult:
        graph = get_compiled_graph()
        cfg = thread_config(ctx.run_id)
        snap = graph.get_state(cfg)
        payload = {
            "decision": decision,
            "feedback": feedback,
            "revise_target": revise_target,
        }

        if snap.next:
            graph.invoke(Command(resume=payload), cfg)
            snap2 = graph.get_state(cfg)
            values = dict(snap2.values or {})
            if snap2.next:
                return self._waiting_envelope(ctx, values), values
            if decision == "reject" or (
                values.get("answer") == "Rejected by human."
            ):
                return (
                    Envelope(
                        trace_id=ctx.trace_id,
                        run_id=ctx.run_id,
                        status=RunStatus.completed,
                        answer=values.get("answer") or "Rejected by human.",
                        citations=self._citations(values),
                        meta=self._meta(ctx, values.get("route")),
                        error=None,
                        hitl=None,
                    ),
                    values,
                )
            if values.get("error_code") == "MAX_ITERATIONS":
                return (
                    self._failed_envelope(
                        ctx,
                        values,
                        code="MAX_ITERATIONS",
                        message=(
                            "reviewer loop exceeded max_iterations={0}".format(
                                ctx.max_iterations
                            )
                        ),
                    ),
                    values,
                )
            return (
                self._to_envelope(ctx, values, RunStatus.completed, hitl=None),
                values,
            )

        state = dict(agent_state)
        if decision == "reject":
            state_dict = state
            return (
                Envelope(
                    trace_id=ctx.trace_id,
                    run_id=ctx.run_id,
                    status=RunStatus.completed,
                    answer="Rejected by human.",
                    citations=self._citations(state),
                    meta=self._meta(ctx, state.get("route")),
                    error=None,
                    hitl=None,
                ),
                state_dict,
            )
        if decision == "approve":
            final = finalize_answer(state)
            return (
                self._to_envelope(ctx, final, RunStatus.completed, hitl=None),
                dict(final),
            )
        if decision == "revise":
            revised = revise_pipeline(
                state,
                revise_target=revise_target,
                feedback=feedback or "",
            )
            if revised.get("error_code") == "MAX_ITERATIONS":
                return (
                    self._failed_envelope(
                        ctx,
                        revised,
                        code="MAX_ITERATIONS",
                        message=(
                            "reviewer loop exceeded max_iterations={0}".format(
                                ctx.max_iterations
                            )
                        ),
                    ),
                    dict(revised),
                )
            if ctx.hitl_enabled:
                return self._waiting_envelope(ctx, revised), dict(revised)
            final = finalize_answer(revised)
            return (
                self._to_envelope(ctx, final, RunStatus.completed, hitl=None),
                dict(final),
            )

        return (
            Envelope(
                trace_id=ctx.trace_id,
                run_id=ctx.run_id,
                status=RunStatus.failed,
                answer=None,
                citations=[],
                meta=self._meta(ctx, state.get("route")),
                error=ErrorObject(
                    code="INVALID_DECISION",
                    message="Unknown decision={0}".format(decision),
                ),
                hitl=None,
            ),
            state,
        )

    def _waiting_envelope(self, ctx: EngineContext, state: AgentState) -> Envelope:
        draft = state.get("draft") or ""
        answer = "(draft)\n{0}".format(draft) if draft else "(draft)"
        risks = list(state.get("risks") or [])
        return Envelope(
            trace_id=ctx.trace_id,
            run_id=ctx.run_id,
            status=RunStatus.waiting_human,
            answer=answer,
            citations=self._citations(state),
            meta=self._meta(ctx, state.get("route")),
            error=None,
            hitl=HitlView(
                required=True,
                actions=["approve", "revise", "reject"],
                preview=HitlPreview(
                    summary=(draft[:500] if draft else "Awaiting human review"),
                    risks=risks,
                ),
            ),
        )

    def _failed_envelope(
        self,
        ctx: EngineContext,
        state: AgentState,
        *,
        code: str,
        message: str,
    ) -> Envelope:
        return Envelope(
            trace_id=ctx.trace_id,
            run_id=ctx.run_id,
            status=RunStatus.failed,
            answer=None,
            citations=self._citations(state),
            meta=self._meta(ctx, state.get("route")),
            error=ErrorObject(code=code, message=message),
            hitl=None,
        )

    def _to_envelope(
        self,
        ctx: EngineContext,
        state: AgentState,
        status: RunStatus,
        hitl: Optional[HitlView],
    ) -> Envelope:
        return Envelope(
            trace_id=ctx.trace_id,
            run_id=ctx.run_id,
            status=status,
            answer=state.get("answer") or "",
            citations=self._citations(state),
            meta=self._meta(ctx, state.get("route")),
            error=None,
            hitl=hitl,
        )

    def _meta(self, ctx: EngineContext, route: Optional[str]) -> Meta:
        r = route if route in ("web", "data", "both", "clarify") else "both"
        return Meta(
            engine=self.name,
            tenant_id=ctx.tenant_id,
            latency_ms=0,
            timeout_ms=ctx.timeout_ms,
            thread_id=ctx.thread_id,
            route=r,
        )

    def _citations(self, state: AgentState) -> List[Citation]:
        raw = list(state.get("citations") or [])
        citations = [_to_citation(c) for c in raw]
        if not citations:
            citations = [
                Citation(
                    type="no_hit",
                    ref="",
                    title="no citations produced",
                    snippet=None,
                )
            ]
        return citations


def _to_citation(raw: Dict[str, Any]) -> Citation:
    ctype = raw.get("type") or "no_hit"
    if ctype not in ("web", "data", "no_hit"):
        ctype = "no_hit"
    return Citation(
        type=ctype,
        ref=raw.get("ref") or "",
        title=raw.get("title") or "",
        snippet=raw.get("snippet"),
    )
