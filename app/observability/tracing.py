"""Thin OTel span helper (no-op if provider unset)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional


@contextmanager
def start_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
) -> Iterator[Any]:
    try:
        from opentelemetry import trace

        tracer = trace.get_tracer("agent-platform-poc")
        with tracer.start_as_current_span(name) as span:
            if attributes:
                for k, v in attributes.items():
                    if v is None:
                        continue
                    span.set_attribute(k, v)
            yield span
    except Exception:
        # Missing SDK / disabled provider → plain no-op context
        yield None
