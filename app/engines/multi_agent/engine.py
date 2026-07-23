"""multi_agent engine: sequential router/search/analyst/review/synthesize."""

from __future__ import annotations

from typing import Any, Dict, List

from app.core.models import (
    Citation,
    Envelope,
    EngineContext,
    Meta,
    RunStatus,
)
from app.engines.multi_agent.graph import run_pipeline
from app.engines.multi_agent.state import AgentState


class MultiAgentEngine:
    name = "multi_agent"

    def run(self, ctx: EngineContext) -> Envelope:
        initial: AgentState = {
            "query": ctx.query,
            "data_path": ctx.data_path,
            "rules_only": ctx.rules_only,
            "citations": [],
            "risks": [],
            "ok": True,
        }
        final = run_pipeline(initial)
        route = final.get("route") or "both"
        answer = final.get("answer") or ""
        raw_citations: List[Dict[str, Any]] = list(final.get("citations") or [])
        citations = [_to_citation(c) for c in raw_citations]
        if not citations:
            citations = [
                Citation(
                    type="no_hit",
                    ref="",
                    title="no citations produced",
                    snippet=None,
                )
            ]

        # No HITL interrupt yet (even if tenant hitl=true).
        return Envelope(
            trace_id=ctx.trace_id,
            run_id=ctx.run_id,
            status=RunStatus.completed,
            answer=answer,
            citations=citations,
            meta=Meta(
                engine=self.name,
                tenant_id=ctx.tenant_id,
                latency_ms=0,
                timeout_ms=ctx.timeout_ms,
                thread_id=ctx.thread_id,
                route=route if route in ("web", "data", "both", "clarify") else "both",
            ),
            error=None,
            hitl=None,
        )


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
