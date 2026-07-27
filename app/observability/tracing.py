"""Thin OTel span helper (no-op if SDK missing)."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

_logger = logging.getLogger(__name__)


@contextmanager
def start_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
) -> Iterator[Any]:
    try:
        from opentelemetry import trace
    except ImportError:
        yield None
        return

    tracer = trace.get_tracer("agent-platform-poc")
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                if v is None:
                    continue
                try:
                    span.set_attribute(k, v)
                except Exception:
                    # Bad attribute type should not abort the request.
                    _logger.debug("otel attribute skipped key=%s", k, exc_info=True)
        yield span
