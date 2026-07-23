"""FastAPI entrypoint: uvicorn app.main:app"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.chat import router as chat_router
from app.core.config import get_settings
from app.core.orchestrator import Orchestrator
from app.core.registry import build_default_registry
from app.store.run_store import RunStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    registry = build_default_registry()
    store = RunStore(settings.run_store_path)
    app.state.orchestrator = Orchestrator(
        registry=registry, store=store, settings=settings
    )
    app.state.settings = settings
    yield


app = FastAPI(
    title="Agent Platform PoC",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(chat_router)


@app.get("/health")
def health() -> dict[str, object]:
    settings = get_settings()
    return {"ok": True, "version": settings.app_version}
