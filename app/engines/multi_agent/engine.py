"""multi_agent engine with sequential HITL pause/resume."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

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
    revise_pipeline,
    run_pipeline,
    run_until_review,
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
            "citations": [],
            "risks": [],
            "ok": True,
        }
        if not ctx.hitl_enabled:
            final = run_pipeline(initial)
            state_dict = self.state_to_dict(final)
            return (
                self._to_envelope(ctx, final, RunStatus.completed, hitl=None),
                state_dict,
            )

        reviewed = run_until_review(initial)
        state_dict = self.state_to_dict(reviewed)
        return self._waiting_envelope(ctx, reviewed), state_dict

    def resume(
        self,
        ctx: EngineContext,
        agent_state: AgentState,
        decision: str,
        feedback: Optional[str] = None,
        revise_target: Optional[str] = None,
    ) -> RunResult:
        if decision == "reject":
            state_dict = dict(agent_state)
            return (
                Envelope(
                    trace_id=ctx.trace_id,
                    run_id=ctx.run_id,
                    status=RunStatus.completed,
                    answer="Rejected by human.",
                    citations=self._citations(agent_state),
                    meta=self._meta(ctx, agent_state.get("route")),
                    error=None,
                    hitl=None,
                ),
                state_dict,
            )

        if decision == "approve":
            final = finalize_answer(agent_state)
            state_dict = self.state_to_dict(final)
            return (
                self._to_envelope(ctx, final, RunStatus.completed, hitl=None),
                state_dict,
            )

        if decision == "revise":
            revised = revise_pipeline(
                agent_state,
                revise_target=revise_target,
                feedback=feedback or "",
            )
            state_dict = self.state_to_dict(revised)
            if ctx.hitl_enabled:
                return self._waiting_envelope(ctx, revised), state_dict
            final = finalize_answer(revised)
            state_dict = self.state_to_dict(final)
            return (
                self._to_envelope(ctx, final, RunStatus.completed, hitl=None),
                state_dict,
            )

        state_dict = dict(agent_state)
        return (
            Envelope(
                trace_id=ctx.trace_id,
                run_id=ctx.run_id,
                status=RunStatus.failed,
                answer=None,
                citations=[],
                meta=self._meta(ctx, agent_state.get("route")),
                error=ErrorObject(
                    code="INVALID_DECISION",
                    message="Unknown decision={0}".format(decision),
                ),
                hitl=None,
            ),
            state_dict,
        )

    def _waiting_envelope(self, ctx: EngineContext, state: AgentState) -> Envelope:
        draft = state.get("draft") or ""
        answer = "(draft)\n{0}".format(draft) if draft else "(draft)"
        citations = self._citations(state)
        risks = list(state.get("risks") or [])
        return Envelope(
            trace_id=ctx.trace_id,
            run_id=ctx.run_id,
            status=RunStatus.waiting_human,
            answer=answer,
            citations=citations,
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

    @staticmethod
    def state_to_dict(state: AgentState) -> Dict[str, Any]:
        return dict(state)


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
