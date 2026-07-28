"""hybrid_rag engine: Router → RAG / T2SQL(+Guardrail) → Synthesis."""

from __future__ import annotations

from typing import Any, Dict, List

from app.core.models import (
    Citation,
    Envelope,
    EngineContext,
    ErrorObject,
    Meta,
    RunStatus,
)
from app.engines.hybrid_rag import db as hybrid_db
from app.engines.hybrid_rag.guardrail import check_sql
from app.engines.hybrid_rag.rag import retrieve
from app.engines.hybrid_rag.router import route_query
from app.engines.hybrid_rag.synthesize import synthesize
from app.engines.hybrid_rag.t2sql import generate_sql


class HybridRagEngine:
    name = "hybrid_rag"

    def run(self, ctx: EngineContext) -> Envelope:
        # Hybrid HITL is off by design (H7); ignore tenant.hitl.
        route = route_query(ctx.query)
        citations: List[Dict[str, Any]] = []
        passages: List[Dict[str, Any]] = []
        sql = ""
        columns: List[str] = []
        rows: List[Dict[str, Any]] = []

        if route in ("rag", "both"):
            passages = retrieve(ctx.query)
            for p in passages:
                citations.append(dict(p["citation"]))

        if route in ("sql", "both"):
            sql = generate_sql(ctx.query)
            ok, reason = check_sql(sql)
            if not ok:
                return Envelope(
                    trace_id=ctx.trace_id,
                    run_id=ctx.run_id,
                    status=RunStatus.failed,
                    answer=None,
                    citations=self._citations(citations),
                    meta=self._meta(ctx, route),
                    error=ErrorObject(
                        code="SQL_GUARDRAIL",
                        message=reason or "SQL rejected by guardrail",
                        details={"sql": sql},
                    ),
                    hitl=None,
                )
            columns, rows = hybrid_db.run_select(sql)
            citations.append(
                {
                    "type": "sql",
                    "ref": sql,
                    "title": "hybrid.db query",
                    "snippet": "rows={0}".format(len(rows)),
                }
            )

        answer = synthesize(
            ctx.query,
            route,
            passages,
            sql,
            columns,
            rows,
        )
        return Envelope(
            trace_id=ctx.trace_id,
            run_id=ctx.run_id,
            status=RunStatus.completed,
            answer=answer,
            citations=self._citations(citations),
            meta=self._meta(ctx, route),
            error=None,
            hitl=None,
        )

    def _meta(self, ctx: EngineContext, route: str) -> Meta:
        r = route if route in ("rag", "sql", "both", "clarify") else "both"
        return Meta(
            engine=self.name,
            tenant_id=ctx.tenant_id,
            latency_ms=0,
            timeout_ms=ctx.timeout_ms,
            thread_id=ctx.thread_id,
            route=r,  # type: ignore[arg-type]
        )

    def _citations(self, raw: List[Dict[str, Any]]) -> List[Citation]:
        out: List[Citation] = []
        for c in raw:
            ctype = c.get("type") or "no_hit"
            if ctype not in ("web", "data", "doc", "sql", "no_hit"):
                ctype = "no_hit"
            out.append(
                Citation(
                    type=ctype,
                    ref=c.get("ref") or "",
                    title=c.get("title") or "",
                    snippet=c.get("snippet"),
                )
            )
        if not out:
            out.append(
                Citation(
                    type="no_hit",
                    ref="",
                    title="no citations produced",
                    snippet=None,
                )
            )
        return out
