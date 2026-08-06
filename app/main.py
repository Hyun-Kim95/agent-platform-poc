"""FastAPI entrypoint: uvicorn app.main:app"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.chat import router as chat_router
from app.api.eval_report import router as eval_report_router
from app.api.feedback import router as feedback_router
from app.api.hitl import router as hitl_router
from app.core.config import get_settings
from app.core.orchestrator import Orchestrator
from app.core.postgres import postgres_available
from app.core.registry import build_default_registry
from app.engines.multi_agent.checkpoint import (
    checkpoint_backend,
    close_checkpointer,
    get_checkpointer,
)
from app.engines.multi_agent.graph import get_compiled_graph
from app.feedback import FeedbackStore
from app.observability import setup_observability
from app.store.run_store import RunStore

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_observability(settings)
    get_checkpointer(settings)
    get_compiled_graph()
    registry = build_default_registry()
    store = RunStore(settings=settings)
    feedback_store = FeedbackStore(settings=settings)
    app.state.orchestrator = Orchestrator(
        registry=registry,
        store=store,
        settings=settings,
        feedback_store=feedback_store,
    )
    app.state.settings = settings
    try:
        yield
    finally:
        close_checkpointer()


app = FastAPI(
    title="Agent Platform PoC",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(chat_router)
app.include_router(hitl_router)
app.include_router(feedback_router)
app.include_router(eval_report_router)


@app.get("/health")
def health() -> Dict[str, Any]:
    settings = get_settings()
    backend = "postgres" if postgres_available(settings) else "sqlite"
    return {
        "ok": True,
        "version": settings.app_version,
        "run_store_backend": backend,
        "checkpoint_backend": checkpoint_backend()
        or ("postgres" if postgres_available(settings) else "sqlite"),
    }


# After API routes: /ui/ -> index.html (html=True)
if STATIC_DIR.is_dir():
    app.mount(
        "/ui",
        StaticFiles(directory=str(STATIC_DIR), html=True),
        name="ui",
    )
