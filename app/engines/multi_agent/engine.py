"""multi_agent engine placeholder — registry routing only."""

from __future__ import annotations

from app.core.models import (
    Citation,
    Envelope,
    EngineContext,
    Meta,
    RunStatus,
)


class MultiAgentEngine:
    name = "multi_agent"

    def run(self, ctx: EngineContext) -> Envelope:
        return Envelope(
            trace_id=ctx.trace_id,
            run_id=ctx.run_id,
            status=RunStatus.completed,
            answer=(
                "[multi_agent placeholder] pipeline not wired yet. "
                "Received: {0}".format(ctx.query)
            ),
            citations=[
                Citation(
                    type="no_hit",
                    ref="",
                    title="placeholder - no web/data yet",
                    snippet=None,
                )
            ],
            meta=Meta(
                engine=self.name,
                tenant_id=ctx.tenant_id,
                latency_ms=0,
                timeout_ms=ctx.timeout_ms,
                thread_id=ctx.thread_id,
                route=None,
            ),
            error=None,
            hitl=None,
        )
