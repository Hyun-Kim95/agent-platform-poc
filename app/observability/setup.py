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
            BatchSpanProcessor,
            ConsoleSpanExporter,
            SimpleSpanProcessor,
        )
    except ImportError:
        _logger.warning("opentelemetry not installed; OTel skipped")
        return

    resource = Resource.create({"service.name": "agent-platform-poc"})
    provider = TracerProvider(resource=resource)
    mode = (settings.otel_exporter or "console").lower()
    exporter = None

    if mode == "console":
        exporter = ConsoleSpanExporter()
    elif mode == "otlp":
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
        except ImportError:
            _logger.warning(
                "otlp exporter not installed; pip install "
                "opentelemetry-exporter-otlp-proto-http"
            )
            return
        endpoint = (settings.otel_exporter_endpoint or "").strip() or (
            "http://127.0.0.1:4318/v1/traces"
        )
        exporter = OTLPSpanExporter(endpoint=endpoint)
    else:
        _logger.warning("unknown OTEL_EXPORTER=%s; OTel skipped", mode)
        return

    if settings.otel_span_processor == "batch":
        provider.add_span_processor(BatchSpanProcessor(exporter))
    else:
        # simple: see spans immediately while learning
        provider.add_span_processor(SimpleSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    _logger.info(
        "OTel exporter=%s processor=%s endpoint=%s",
        mode,
        settings.otel_span_processor,
        settings.otel_exporter_endpoint if mode == "otlp" else "-",
    )
