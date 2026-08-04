"""multi_agent engine backed by LangGraph (+ cold-resume fallback)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from langgraph.types import Command

from app.core.citations import citations_or_fallback
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
from app.engines.multi_agent.text_sanitize import sanitize_snippet

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
                        meta=self._meta(ctx, values.get("route"), values),
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
                    meta=self._meta(ctx, state.get("route"), state),
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
                meta=self._meta(ctx, state.get("route"), state),
                error=ErrorObject(
                    code="INVALID_DECISION",
                    message="Unknown decision={0}".format(decision),
                ),
                hitl=None,
            ),
            state,
        )

    def _build_hitl_preview(self, state: AgentState) -> HitlPreview:
        route = state.get("route") or "both"
        data = state.get("data_summary") or "no data summary"
        web_titles = []
        for c in state.get("citations") or []:
            if c.get("type") != "web":
                continue
            t = sanitize_snippet(c.get("title") or "", max_len=80)
            if t:
                web_titles.append(t)
        fb = state.get("last_feedback")
        tgt = state.get("last_revise_target")
        lines = [
            "Data: {0}".format(data),
            "Route: {0}".format(route),
            "Web: {0}".format(
                ", ".join(web_titles[:5]) if web_titles else "(none)"
            ),
        ]
        if fb:
            lines.append("Last feedback: {0}".format(fb))
        if tgt:
            lines.append("Last revise_target: {0}".format(tgt))
        return HitlPreview(
            summary="\n".join(lines),
            risks=list(state.get("risks") or []),
            route=route,
            data_summary=data,
            web_titles=web_titles[:8],
            last_feedback=fb,
            last_revise_target=tgt,
        )

    def _waiting_envelope(self, ctx: EngineContext, state: AgentState) -> Envelope:
        draft = state.get("draft") or ""
        answer = "(draft)\n{0}".format(draft) if draft else "(draft)"
        preview = self._build_hitl_preview(state)
        return Envelope(
            trace_id=ctx.trace_id,
            run_id=ctx.run_id,
            status=RunStatus.waiting_human,
            answer=answer,
            citations=self._citations(state),
            meta=self._meta(ctx, state.get("route"), state),
            error=None,
            hitl=HitlView(
                required=True,
                actions=["approve", "revise", "reject"],
                preview=preview,
                last_feedback=state.get("last_feedback"),
                last_revise_target=state.get("last_revise_target"),
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
            meta=self._meta(ctx, state.get("route"), state),
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
            meta=self._meta(ctx, state.get("route"), state),
            error=None,
            hitl=hitl,
        )

    def _meta(
        self,
        ctx: EngineContext,
        route: Optional[str],
        state: Optional[AgentState] = None,
    ) -> Meta:
        r = route if route in ("web", "data", "both", "clarify") else "both"
        src = None
        if state is not None:
            raw = state.get("web_search_source")
            if raw in ("tavily", "mock"):
                src = raw
        return Meta(
            engine=self.name,
            tenant_id=ctx.tenant_id,
            latency_ms=0,
            timeout_ms=ctx.timeout_ms,
            thread_id=ctx.thread_id,
            route=r,
            web_search_source=src,
        )

    def _citations(self, state: AgentState) -> List[Citation]:
        raw = list(state.get("citations") or [])
        return citations_or_fallback(raw)
