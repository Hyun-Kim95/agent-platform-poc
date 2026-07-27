"""Boot-time observability wiring (idempotent)."""

from __future__ import annotations

import logging
import os

from app.core.config import Settings

_logger = logging.getLogger(__name__)
_initialized = False


def setup_observability(settings: Settings) -> None:
    global _initialized
    if _initialized:
        return
    _setup_langsmith(settings)
    _setup_otel(settings)
    _initialized = True


def _setup_langsmith(settings: Settings) -> None:
    key = (settings.langsmith_api_key or "").strip()
    want = bool(settings.langsmith_tracing) or bool(key)
    if want and key:
        # LangGraph / langchain-core read these env vars.
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = key
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.langsmith_project)
        os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)
        _logger.info(
            "LangSmith tracing enabled (project=%s)", settings.langsmith_project
        )
    else:
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        _logger.info("LangSmith tracing disabled (no-op)")


def _setup_otel(settings: Settings) -> None:
    if not settings.otel_enabled or settings.otel_exporter == "none":
        _logger.info("OTel disabled")
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            ConsoleSpanExporter,
            SimpleSpanProcessor,
        )
    except ImportError:
        _logger.warning("opentelemetry not installed; OTel skipped")
        return

    resource = Resource.create({"service.name": "agent-platform-poc"})
    provider = TracerProvider(resource=resource)
    if settings.otel_exporter == "console":
        # SimpleSpanProcessor: see spans immediately while learning
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    _logger.info("OTel console exporter enabled")
