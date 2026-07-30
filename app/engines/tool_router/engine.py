"""tool_router engine: route → tools → synthesize."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.citations import citations_or_fallback
from app.core.config import get_settings
from app.core.models import (
    Envelope,
    EngineContext,
    Meta,
    RunStatus,
)
from app.engines.tool_router.router import route_tools
from app.engines.tool_router.synthesize import synthesize
from app.engines.tool_router.tools import run_tool


class ToolRouterEngine:
    name = "tool_router"

    def run(self, ctx: EngineContext) -> Envelope:
        # HITL off by design for this engine.
        cfg = get_settings()
        tools, usage, route_source = route_tools(
            ctx.query,
            rules_only=ctx.rules_only,
            settings=cfg,
        )

        results: List[Dict[str, Any]] = []
        citations: List[Dict[str, Any]] = []
        for name in tools:
            result = run_tool(name, ctx.query)
            results.append(result)
            if result.get("ok"):
                citations.append(
                    {
                        "type": "tool",
                        "ref": name,
                        "title": "tool:{0}".format(name),
                        "snippet": str(result.get("text") or "")[:240],
                    }
                )
            else:
                citations.append(
                    {
                        "type": "no_hit",
                        "ref": name,
                        "title": "tool miss:{0}".format(name),
                        "snippet": str(result.get("text") or ""),
                    }
                )

        if not tools:
            citations.append(
                {
                    "type": "no_hit",
                    "ref": "",
                    "title": "no tool selected",
                    "snippet": "route_source={0}".format(route_source),
                }
            )

        answer = synthesize(
            ctx.query, results, route_source=route_source
        )
        route_meta = self._route_meta(tools)
        return Envelope(
            trace_id=ctx.trace_id,
            run_id=ctx.run_id,
            status=RunStatus.completed,
            answer=answer,
            citations=citations_or_fallback(citations),
            meta=Meta(
                engine=self.name,
                tenant_id=ctx.tenant_id,
                latency_ms=0,
                timeout_ms=ctx.timeout_ms,
                thread_id=ctx.thread_id,
                route=route_meta,  # type: ignore[arg-type]
                usage=usage,
            ),
            error=None,
            hitl=None,
        )

    @staticmethod
    def _route_meta(tools: List[str]) -> Optional[str]:
        if not tools:
            return "none"
        if len(tools) >= 2:
            return "both"
        return tools[0]
