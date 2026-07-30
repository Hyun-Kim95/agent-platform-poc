"""Orchestrator: tenant → engine → persist → envelope (+ HITL resume)."""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set, Tuple, Union

from app.core.config import Settings, TenantConfig, get_settings, load_tenant
from app.core.models import (
    ChatRequest,
    Envelope,
    EngineContext,
    ErrorObject,
    FeedbackRequest,
    FeedbackResponse,
    HitlRequest,
    Meta,
    RunStatus,
)
from app.core.registry import EngineRegistry, build_default_registry
from app.engines.base import ResumableEngine
from app.feedback import FeedbackAppendError, FeedbackStore
from app.llm.usage import estimate_usage
from app.observability import append_run_event, start_span
from app.store.run_store import RunRecord, RunStore


def new_trace_id() -> str:
    return str(uuid.uuid4())


def new_run_id() -> str:
    return "run_{0}".format(uuid.uuid4().hex)


def _parse_utc(ts: str) -> datetime:
    # stored as ...Z
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def _unpack_engine_result(
    raw: Union[Envelope, Tuple[Envelope, Dict[str, Any]]],
) -> Tuple[Envelope, Dict[str, Any]]:
    if isinstance(raw, tuple):
        return raw[0], dict(raw[1] or {})
    return raw, {}


class Orchestrator:
    def __init__(
        self,
        registry: Optional[EngineRegistry] = None,
        store: Optional[RunStore] = None,
        settings: Optional[Settings] = None,
        feedback_store: Optional[FeedbackStore] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.registry = registry or build_default_registry()
        self.store = store or RunStore(settings=self.settings)
        self.feedback_store = feedback_store or FeedbackStore(
            self.settings.feedback_log_path
        )
        self._hitl_locks: Set[str] = set()
        self._lock = threading.Lock()

    def submit_feedback(
        self, body: FeedbackRequest
    ) -> Union[FeedbackResponse, ErrorObject]:
        """Return FeedbackResponse or ErrorObject (RUN_NOT_FOUND / INTERNAL)."""
        t0 = time.perf_counter()
        with start_span(
            "orchestrator.feedback",
            {"run_id": body.run_id, "rating": body.rating},
        ) as span:
            record = self.store.get(body.run_id)
            if record is None:
                return ErrorObject(
                    code="RUN_NOT_FOUND",
                    message="run_id not found: {0}".format(body.run_id),
                    details={"run_id": body.run_id},
                )
            try:
                saved = self.feedback_store.append(
                    run_id=body.run_id,
                    rating=body.rating,
                    comment=body.comment,
                    labels=body.labels,
                )
            except FeedbackAppendError as exc:
                return ErrorObject(
                    code="INTERNAL",
                    message=str(exc),
                    details={
                        "run_id": body.run_id,
                        "path": str(self.feedback_store.path),
                    },
                )

            latency_ms = int((time.perf_counter() - t0) * 1000)
            if span is not None:
                try:
                    span.set_attribute("feedback_id", saved["feedback_id"])
                    span.set_attribute("latency_ms", latency_ms)
                except Exception:
                    pass

            append_run_event(
                self.settings.jsonl_log_path,
                event="feedback",
                trace_id=new_trace_id(),
                run_id=body.run_id,
                engine=record.engine,
                tenant_id=record.tenant_id,
                status=record.status,
                latency_ms=latency_ms,
                extra={
                    "feedback_id": saved["feedback_id"],
                    "rating": body.rating,
                },
            )
            return FeedbackResponse(
                ok=True,
                feedback_id=saved["feedback_id"],
                run_id=body.run_id,
                stored_at=saved["stored_at"],
            )

    def _ensure_usage(self, result: Envelope, query: str) -> None:
        if result.meta.usage is not None:
            return
        if not self.settings.usage_estimate_enabled:
            return
        result.meta.usage = estimate_usage(
            query or "",
            result.answer or "",
            self.settings.llm_model,
        )

    def _log_envelope(self, event: str, result: Envelope) -> None:
        err = result.error.code if result.error else None
        extra = None
        if result.meta.usage is not None:
            extra = {"usage": result.meta.usage.model_dump()}
        append_run_event(
            self.settings.jsonl_log_path,
            event=event,
            trace_id=result.trace_id,
            run_id=result.run_id,
            engine=result.meta.engine,
            tenant_id=result.meta.tenant_id,
            status=result.status.value,
            latency_ms=result.meta.latency_ms,
            error_code=err,
            extra=extra,
        )

    def chat(self, req: ChatRequest) -> Envelope:
        with start_span(
            "orchestrator.chat",
            {
                "tenant_id": req.tenant_id,
                "engine": req.engine or "",
            },
        ) as span:
            result = self._chat_impl(req)
            if span is not None:
                span.set_attribute("run_id", result.run_id)
                span.set_attribute("trace_id", result.trace_id)
                span.set_attribute("status", result.status.value)
                span.set_attribute("latency_ms", result.meta.latency_ms)
            self._ensure_usage(result, req.query.strip())
            self._log_envelope("chat", result)
            return result

    def _chat_impl(self, req: ChatRequest) -> Envelope:
        started = time.perf_counter()
        started_at = RunStore.now()
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
                started_at=started_at,
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
                started_at=started_at,
            )

        rules_only = tenant.rules_only or self.settings.rules_only
        force_insuf = bool(tenant.force_reviewer_insufficient) or bool(
            self.settings.force_reviewer_insufficient
        )
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
            force_reviewer_insufficient=force_insuf,
        )

        result, agent_state = _unpack_engine_result(engine.run(ctx))
        latency_ms = int((time.perf_counter() - started) * 1000)
        result.meta.latency_ms = latency_ms
        result.meta.timeout_ms = tenant.timeout_ms
        result.meta.tenant_id = tenant.tenant_id
        result.meta.thread_id = req.thread_id
        result.meta.engine = engine.name
        result.trace_id = trace_id
        result.run_id = run_id

        if not agent_state and result.status == RunStatus.waiting_human:
            agent_state = {
                "query": req.query.strip(),
                "data_path": tenant.data_path,
                "rules_only": rules_only,
                "force_reviewer_insufficient": force_insuf,
                "route": result.meta.route,
                "citations": [c.model_dump() for c in result.citations],
                "risks": (
                    result.hitl.preview.risks
                    if result.hitl and result.hitl.preview
                    else []
                ),
                "draft": (result.answer or "").replace("(draft)\n", "", 1),
                "answer": "",
                "ok": True,
            }

        self._persist_envelope(
            result,
            agent_state=agent_state,
            started_at=started_at,
            ctx_extras={
                "query": req.query.strip(),
                "data_path": tenant.data_path,
                "rules_only": rules_only,
                "hitl_enabled": tenant.hitl,
                "timeout_ms": tenant.timeout_ms,
                "max_iterations": tenant.max_iterations,
                "force_reviewer_insufficient": force_insuf,
            },
            created_at=started_at,
        )
        return result

    def hitl(self, run_id: str, body: HitlRequest) -> Envelope:
        with start_span(
            "orchestrator.hitl",
            {"run_id": run_id, "decision": body.decision},
        ) as span:
            result = self._hitl_impl(run_id, body)
            if span is not None:
                span.set_attribute("trace_id", result.trace_id)
                span.set_attribute("status", result.status.value)
                span.set_attribute("latency_ms", result.meta.latency_ms)
            query = ""
            record = self.store.get(run_id)
            if record is not None and isinstance(record.graph_state, dict):
                query = str(record.graph_state.get("query") or "")
            self._ensure_usage(result, query)
            self._log_envelope("hitl", result)
            return result

    def _hitl_impl(self, run_id: str, body: HitlRequest) -> Envelope:
        started = time.perf_counter()
        trace_id = new_trace_id()

        record = self.store.get(run_id)
        if record is None:
            return Envelope(
                trace_id=trace_id,
                run_id=run_id,
                status=RunStatus.failed,
                answer=None,
                citations=[],
                meta=Meta(
                    engine="unknown",
                    tenant_id="unknown",
                    latency_ms=0,
                    timeout_ms=0,
                    thread_id=None,
                    route=None,
                ),
                error=ErrorObject(code="RUN_NOT_FOUND", message="run_id not found"),
                hitl=None,
            )

        gs = dict(record.graph_state or {})
        timeout_ms = int(gs.get("timeout_ms") or 120_000)
        started_at = gs.get("started_at") or record.created_at
        try:
            elapsed_ms = int(
                (datetime.now(timezone.utc) - _parse_utc(started_at)).total_seconds()
                * 1000
            )
        except Exception:
            return Envelope(
                trace_id=trace_id,
                run_id=run_id,
                status=RunStatus.failed,
                answer=None,
                citations=[],
                meta=Meta(
                    engine=record.engine,
                    tenant_id=record.tenant_id,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    timeout_ms=timeout_ms,
                    thread_id=record.thread_id,
                    route=gs.get("route"),
                ),
                error=ErrorObject(
                    code="INTERNAL",
                    message="invalid started_at in run store: {0}".format(started_at),
                ),
                hitl=None,
            )
        if elapsed_ms > timeout_ms:
            result = Envelope(
                trace_id=trace_id,
                run_id=run_id,
                status=RunStatus.failed,
                answer=None,
                citations=[],
                meta=Meta(
                    engine=record.engine,
                    tenant_id=record.tenant_id,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    timeout_ms=timeout_ms,
                    thread_id=record.thread_id,
                    route=gs.get("route"),
                ),
                error=ErrorObject(
                    code="TIMEOUT",
                    message="Orchestrator exceeded timeout_ms={0}".format(timeout_ms),
                ),
                hitl=None,
            )
            self._persist_envelope(
                result,
                agent_state=gs.get("agent_state") or {},
                started_at=started_at,
                ctx_extras=gs,
                created_at=record.created_at,
            )
            return result

        if record.status != RunStatus.waiting_human.value:
            return Envelope(
                trace_id=trace_id,
                run_id=run_id,
                status=RunStatus.failed,
                answer=None,
                citations=[],
                meta=Meta(
                    engine=record.engine,
                    tenant_id=record.tenant_id,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    timeout_ms=timeout_ms,
                    thread_id=record.thread_id,
                    route=gs.get("route"),
                ),
                error=ErrorObject(
                    code="INVALID_HITL_STATE",
                    message="run status is {0}, expected waiting_human".format(
                        record.status
                    ),
                ),
                hitl=None,
            )

        with self._lock:
            if run_id in self._hitl_locks:
                return Envelope(
                    trace_id=trace_id,
                    run_id=run_id,
                    status=RunStatus.failed,
                    answer=None,
                    citations=[],
                    meta=Meta(
                        engine=record.engine,
                        tenant_id=record.tenant_id,
                        latency_ms=int((time.perf_counter() - started) * 1000),
                        timeout_ms=timeout_ms,
                        thread_id=record.thread_id,
                        route=gs.get("route"),
                    ),
                    error=ErrorObject(
                        code="CONFLICT",
                        message="another hitl request is in progress for this run_id",
                    ),
                    hitl=None,
                )
            self._hitl_locks.add(run_id)

        try:
            engine = self.registry.get(record.engine)
            if engine is None or not isinstance(engine, ResumableEngine):
                return Envelope(
                    trace_id=trace_id,
                    run_id=run_id,
                    status=RunStatus.failed,
                    answer=None,
                    citations=[],
                    meta=Meta(
                        engine=record.engine,
                        tenant_id=record.tenant_id,
                        latency_ms=0,
                        timeout_ms=timeout_ms,
                        thread_id=record.thread_id,
                        route=gs.get("route"),
                    ),
                    error=ErrorObject(
                        code="INVALID_HITL_STATE",
                        message="engine does not support resume",
                    ),
                    hitl=None,
                )

            agent_state = dict(gs.get("agent_state") or {})
            ctx = EngineContext(
                tenant_id=record.tenant_id,
                query=gs.get("query") or agent_state.get("query") or "",
                thread_id=record.thread_id,
                trace_id=trace_id,
                run_id=run_id,
                timeout_ms=timeout_ms,
                hitl_enabled=bool(gs.get("hitl_enabled", True)),
                max_iterations=int(gs.get("max_iterations") or 8),
                data_path=gs.get("data_path") or "samples/mini.csv",
                rules_only=bool(gs.get("rules_only", False)),
                force_reviewer_insufficient=bool(
                    gs.get("force_reviewer_insufficient", False)
                ),
            )
            result, new_state = _unpack_engine_result(
                engine.resume(
                    ctx,
                    agent_state,
                    decision=body.decision,
                    feedback=body.feedback,
                    revise_target=body.revise_target,
                )
            )
            result.trace_id = trace_id
            result.run_id = run_id
            result.meta.latency_ms = int((time.perf_counter() - started) * 1000)
            result.meta.timeout_ms = timeout_ms
            result.meta.tenant_id = record.tenant_id
            result.meta.thread_id = record.thread_id
            result.meta.engine = record.engine

            self._persist_envelope(
                result,
                agent_state=new_state or agent_state,
                started_at=started_at,
                ctx_extras=gs,
                created_at=record.created_at,
            )
            return result
        finally:
            with self._lock:
                self._hitl_locks.discard(run_id)

    def _persist_envelope(
        self,
        result: Envelope,
        *,
        agent_state: Dict[str, Any],
        started_at: str,
        ctx_extras: Dict[str, Any],
        created_at: str,
    ) -> None:
        now = RunStore.now()
        error_code = result.error.code if result.error else None
        state: Dict[str, Any] = {
            "started_at": started_at,
            "query": ctx_extras.get("query"),
            "data_path": ctx_extras.get("data_path"),
            "rules_only": ctx_extras.get("rules_only"),
            "hitl_enabled": ctx_extras.get("hitl_enabled"),
            "timeout_ms": ctx_extras.get("timeout_ms") or result.meta.timeout_ms,
            "max_iterations": ctx_extras.get("max_iterations"),
            "force_reviewer_insufficient": ctx_extras.get(
                "force_reviewer_insufficient"
            ),
            "route": result.meta.route,
            "answer": result.answer,
            "citations": [c.model_dump() for c in result.citations],
            "agent_state": agent_state,
        }
        self.store.save(
            RunRecord(
                run_id=result.run_id,
                status=result.status.value,
                graph_state=state,
                tenant_id=result.meta.tenant_id,
                engine=result.meta.engine,
                thread_id=result.meta.thread_id,
                created_at=created_at,
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
        started_at: Optional[str] = None,
    ) -> Envelope:
        latency_ms = int((time.perf_counter() - started) * 1000)
        tenant_id = tenant.tenant_id if tenant else req.tenant_id
        sa = started_at or RunStore.now()
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
        self._persist_envelope(
            result,
            agent_state={},
            started_at=sa,
            ctx_extras={"query": req.query, "timeout_ms": timeout_ms},
            created_at=sa,
        )
        return result
