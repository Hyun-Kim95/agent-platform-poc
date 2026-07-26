"""multi_agent engine with sequential HITL pause/resume."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

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


class MultiAgentEngine:
    name = "multi_agent"

    def __init__(self) -> None:
        self._last_state: Dict[str, Any] = {}

    def run(self, ctx: EngineContext) -> Envelope:
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
            self._last_state = self.state_to_dict(final)
            return self._to_envelope(ctx, final, RunStatus.completed, hitl=None)

        reviewed = run_until_review(initial)
        self._last_state = self.state_to_dict(reviewed)
        return self._waiting_envelope(ctx, reviewed)

    def resume(
        self,
        ctx: EngineContext,
        agent_state: AgentState,
        decision: str,
        feedback: Optional[str] = None,
        revise_target: Optional[str] = None,
    ) -> Envelope:
        if decision == "reject":
            self._last_state = dict(agent_state)
            return Envelope(
                trace_id=ctx.trace_id,
                run_id=ctx.run_id,
                status=RunStatus.completed,
                answer="Rejected by human.",
                citations=[],
                meta=self._meta(ctx, agent_state.get("route")),
                error=None,
                hitl=None,
            )

        if decision == "approve":
            final = finalize_answer(agent_state)
            self._last_state = self.state_to_dict(final)
            return self._to_envelope(ctx, final, RunStatus.completed, hitl=None)

        if decision == "revise":
            revised = revise_pipeline(
                agent_state,
                revise_target=revise_target,
                feedback=feedback or "",
            )
            self._last_state = self.state_to_dict(revised)
            if ctx.hitl_enabled:
                return self._waiting_envelope(ctx, revised)
            final = finalize_answer(revised)
            self._last_state = self.state_to_dict(final)
            return self._to_envelope(ctx, final, RunStatus.completed, hitl=None)

        self._last_state = dict(agent_state)
        return Envelope(
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

    @staticmethod
    def dict_to_state(data: Dict[str, Any]) -> AgentState:
        return data  # type: ignore[return-value]


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
