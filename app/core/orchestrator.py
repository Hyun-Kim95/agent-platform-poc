"""Orchestrator: tenant → engine → persist → envelope."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional

from app.core.config import Settings, TenantConfig, get_settings, load_tenant
from app.core.models import (
    ChatRequest,
    Envelope,
    EngineContext,
    ErrorObject,
    Meta,
    RunStatus,
)
from app.core.registry import EngineRegistry, build_default_registry
from app.store.run_store import RunRecord, RunStore


def new_trace_id() -> str:
    return str(uuid.uuid4())


def new_run_id() -> str:
    return "run_{0}".format(uuid.uuid4().hex)


class Orchestrator:
    def __init__(
        self,
        registry: Optional[EngineRegistry] = None,
        store: Optional[RunStore] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.registry = registry or build_default_registry()
        self.store = store or RunStore(self.settings.run_store_path)

    def chat(self, req: ChatRequest) -> Envelope:
        started = time.perf_counter()
        trace_id = new_trace_id()
        run_id = new_run_id()

        tenant = load_tenant(req.tenant_id)
        if tenant is None:
            return self._failed_early(
                trace_id=trace_id,
                run_id=run_id,
                req=req,
                code="TENANT_NOT_FOUND",
                message="Unknown tenant_id={0}".format(req.tenant_id),
                started=started,
                timeout_ms=120_000,
                engine=req.engine or "multi_agent",
            )

        engine_name = req.engine or tenant.default_engine
        engine = self.registry.get(engine_name)
        if engine is None:
            return self._failed_early(
                trace_id=trace_id,
                run_id=run_id,
                req=req,
                code="ENGINE_NOT_FOUND",
                message="Unknown engine={0}".format(engine_name),
                started=started,
                timeout_ms=tenant.timeout_ms,
                engine=engine_name,
                tenant=tenant,
            )

        rules_only = tenant.rules_only or self.settings.rules_only
        ctx = EngineContext(
            tenant_id=tenant.tenant_id,
            query=req.query.strip(),
            thread_id=req.thread_id,
            trace_id=trace_id,
            run_id=run_id,
            timeout_ms=tenant.timeout_ms,
            hitl_enabled=tenant.hitl,
            max_iterations=tenant.max_iterations,
            data_path=tenant.data_path,
            rules_only=rules_only,
        )

        result = engine.run(ctx)
        latency_ms = int((time.perf_counter() - started) * 1000)
        result.meta.latency_ms = latency_ms
        result.meta.timeout_ms = tenant.timeout_ms
        result.meta.tenant_id = tenant.tenant_id
        result.meta.thread_id = req.thread_id
        result.meta.engine = engine.name
        result.trace_id = trace_id
        result.run_id = run_id

        self._persist(result, query=req.query)
        return result

    def _persist(self, result: Envelope, query: str) -> None:
        now = RunStore.now()
        error_code = result.error.code if result.error else None
        state: Dict[str, Any] = {
            "query": query,
            "answer": result.answer,
            "citations": [c.model_dump() for c in result.citations],
            "route": result.meta.route,
            "phase": "phase1_skeleton",
        }
        self.store.save(
            RunRecord(
                run_id=result.run_id,
                status=result.status.value,
                graph_state=state,
                tenant_id=result.meta.tenant_id,
                engine=result.meta.engine,
                thread_id=result.meta.thread_id,
                created_at=now,
                updated_at=now,
                error_code=error_code,
            )
        )

    def _failed_early(
        self,
        *,
        trace_id: str,
        run_id: str,
        req: ChatRequest,
        code: str,
        message: str,
        started: float,
        timeout_ms: int,
        engine: str,
        tenant: Optional[TenantConfig] = None,
    ) -> Envelope:
        latency_ms = int((time.perf_counter() - started) * 1000)
        tenant_id = tenant.tenant_id if tenant else req.tenant_id
        result = Envelope(
            trace_id=trace_id,
            run_id=run_id,
            status=RunStatus.failed,
            answer=None,
            citations=[],
            meta=Meta(
                engine=engine,
                tenant_id=tenant_id,
                latency_ms=latency_ms,
                timeout_ms=timeout_ms,
                thread_id=req.thread_id,
                route=None,
            ),
            error=ErrorObject(code=code, message=message),
            hitl=None,
        )
        self._persist(result, query=req.query)
        return result
