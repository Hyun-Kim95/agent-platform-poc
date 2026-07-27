"""
Observability smoke: chat writes JSONL with trace_id/engine/latency_ms.

Uses tenant=internal (completed path).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

import httpx

BASE = os.environ.get("AGENT_API_BASE", "http://127.0.0.1:8000")
JSONL = Path(os.environ.get("JSONL_LOG_PATH", "data/runs.jsonl"))


def main() -> int:
    before = JSONL.stat().st_size if JSONL.is_file() else 0
    body: Dict[str, Any] = {}
    with httpx.Client(base_url=BASE, timeout=60.0) as client:
        r = client.post(
            "/v1/chat",
            json={
                "tenant_id": "internal",
                "engine": "multi_agent",
                "query": "samples/mini.csv 기준 매출 합계를 알려줘.",
            },
        )
        r.raise_for_status()
        body = r.json()
        assert body["status"] == "completed", body
        assert body.get("trace_id"), body

    assert JSONL.is_file(), "JSONL log missing: {0}".format(JSONL)
    raw = JSONL.read_bytes()
    if before and before < len(raw):
        chunk = raw[before:].decode("utf-8")
    else:
        chunk = raw.decode("utf-8")
    lines = [ln for ln in chunk.strip().splitlines() if ln.strip()]
    assert lines, "no JSONL lines after chat"
    last = json.loads(lines[-1])
    assert last.get("event") == "chat", last
    assert last.get("trace_id") == body["trace_id"], last
    assert last.get("engine") == "multi_agent", last
    assert "latency_ms" in last, last
    print("Observability smoke OK:", last)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except httpx.ConnectError:
        print(
            "ERROR: start API first: uvicorn app.main:app --port 8000",
            file=sys.stderr,
        )
        raise SystemExit(1)
