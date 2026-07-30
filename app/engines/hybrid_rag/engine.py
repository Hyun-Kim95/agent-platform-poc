"""hybrid_rag engine: Router → RAG / T2SQL(+Guardrail) → Synthesis."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.citations import citations_or_fallback
from app.core.config import get_settings
from app.core.models import (
    Envelope,
    EngineContext,
    ErrorObject,
    Meta,
    RunStatus,
    TokenUsage,
)
from app.engines.hybrid_rag import db as hybrid_db
from app.engines.hybrid_rag.guardrail import check_sql
from app.engines.hybrid_rag.rag import retrieve
from app.engines.hybrid_rag.router import route_query
from app.engines.hybrid_rag.synthesize import synthesize
from app.engines.hybrid_rag.t2sql import generate_sql
from app.llm.usage import merge_usage


class HybridRagEngine:
    name = "hybrid_rag"

    def run(self, ctx: EngineContext) -> Envelope:
        # Hybrid HITL is off by design (H7); ignore tenant.hitl.
        route, route_usage, route_source = route_query(
            ctx.query,
            rules_only=ctx.rules_only,
        )
        citations: List[Dict[str, Any]] = []
        passages: List[Dict[str, Any]] = []
        rag_source = "none"
        embed_usage: Optional[TokenUsage] = None
        sql = ""
        sql_source = "template"
        sql_usage: Optional[TokenUsage] = None
        columns: List[str] = []
        rows: List[Dict[str, Any]] = []

        if route in ("rag", "both"):
            passages, rag_source, embed_usage = retrieve(
                ctx.query,
                settings=get_settings(),
            )
            for p in passages:
                citations.append(dict(p["citation"]))

        if route in ("sql", "both"):
            sql, sql_usage, sql_source = generate_sql(
                ctx.query,
                rules_only=ctx.rules_only,
            )
            ok, reason = check_sql(sql)
            usage = merge_usage(
                merge_usage(route_usage, embed_usage),
                sql_usage,
            )
            if not ok:
                return Envelope(
                    trace_id=ctx.trace_id,
                    run_id=ctx.run_id,
                    status=RunStatus.failed,
                    answer=None,
                    citations=citations_or_fallback(citations),
                    meta=self._meta(
                        ctx,
                        route,
                        usage=usage,
                        rag_source=rag_source,
                    ),
                    error=ErrorObject(
                        code="SQL_GUARDRAIL",
                        message=reason or "SQL rejected by guardrail",
                        details={
                            "sql": sql,
                            "sql_source": sql_source,
                            "route_source": route_source,
                        },
                    ),
                    hitl=None,
                )
            columns, rows = hybrid_db.run_select(sql)
            citations.append(
                {
                    "type": "sql",
                    "ref": sql,
                    "title": "hybrid.db query ({0})".format(sql_source),
                    "snippet": "rows={0}".format(len(rows)),
                }
            )

        usage = merge_usage(
            merge_usage(route_usage, embed_usage),
            sql_usage,
        )
        answer = synthesize(
            ctx.query,
            route,
            passages,
            sql,
            columns,
            rows,
            route_source=route_source,
        )
        return Envelope(
            trace_id=ctx.trace_id,
            run_id=ctx.run_id,
            status=RunStatus.completed,
            answer=answer,
            citations=citations_or_fallback(citations),
            meta=self._meta(
                ctx,
                route,
                usage=usage,
                rag_source=rag_source,
            ),
            error=None,
            hitl=None,
        )

    def _meta(
        self,
        ctx: EngineContext,
        route: str,
        *,
        usage: Optional[TokenUsage] = None,
        rag_source: Optional[str] = None,
    ) -> Meta:
        r = route if route in ("rag", "sql", "both", "clarify") else "both"
        rs = rag_source if rag_source in ("vector", "keyword", "none") else None
        return Meta(
            engine=self.name,
            tenant_id=ctx.tenant_id,
            latency_ms=0,
            timeout_ms=ctx.timeout_ms,
            thread_id=ctx.thread_id,
            route=r,  # type: ignore[arg-type]
            usage=usage,
            rag_source=rs,  # type: ignore[arg-type]
        )
