"""Append-only JSONL run log (local learning artifact)."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_lock = threading.Lock()
_logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_run_event(
    path: str,
    *,
    event: str,
    trace_id: str,
    run_id: str,
    engine: str,
    tenant_id: str,
    status: str,
    latency_ms: int,
    error_code: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Write one JSON object per line. Never raises to callers."""
    record: Dict[str, Any] = {
        "ts": _utc_now(),
        "event": event,
        "trace_id": trace_id,
        "run_id": run_id,
        "engine": engine,
        "tenant_id": tenant_id,
        "status": status,
        "latency_ms": latency_ms,
    }
    if error_code:
        record["error_code"] = error_code
    if extra:
        record.update(extra)
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False)
        with _lock:
            with p.open("a", encoding="utf-8") as f:
                f.write(line)
                f.write("\n")
    except Exception:
        # Observability must not break the API; do not swallow silently.
        _logger.warning("jsonl append failed path=%s", path, exc_info=True)
