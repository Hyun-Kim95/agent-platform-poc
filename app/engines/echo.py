"""Echo stub engine — proves Registry branching via meta.engine."""

from __future__ import annotations

from app.core.models import (
    Citation,
    Envelope,
    EngineContext,
    Meta,
    RunStatus,
)


class EchoEngine:
    name = "echo"

    def run(self, ctx: EngineContext) -> Envelope:
        # Tenant hitl is ignored: echo never waits for human.
        return Envelope(
            trace_id=ctx.trace_id,
            run_id=ctx.run_id,
            status=RunStatus.completed,
            answer=f"[echo] {ctx.query}",
            citations=[
                Citation(
                    type="no_hit",
                    ref="",
                    title="echo has no external sources",
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
