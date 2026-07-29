"""
Token/cost lite smoke: Envelope.meta.usage + JSONL usage object.
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
    with httpx.Client(base_url=BASE, timeout=60.0) as client:
        r = client.post(
            "/v1/chat",
            json={
                "tenant_id": "internal",
                "engine": "hybrid_rag",
                "query": "환불 정책 알려줘",
            },
        )
        r.raise_for_status()
        body = r.json()

    assert body["status"] == "completed", body
    usage = (body.get("meta") or {}).get("usage")
    assert usage is not None, body.get("meta")
    assert usage.get("total_tokens", 0) > 0, usage
    assert "cost_usd" in usage, usage
    assert usage.get("estimated") is True, usage
    assert usage.get("model"), usage

    assert JSONL.is_file(), "JSONL missing: {0}".format(JSONL)
    raw = JSONL.read_bytes()
    chunk = (
        raw[before:].decode("utf-8")
        if before and before < len(raw)
        else raw.decode("utf-8")
    )
    lines = [ln for ln in chunk.strip().splitlines() if ln.strip()]
    assert lines, "no JSONL lines"
    last: Dict[str, Any] = json.loads(lines[-1])
    assert last.get("trace_id") == body["trace_id"], last
    ju = last.get("usage")
    assert isinstance(ju, dict), last
    assert ju.get("total_tokens", 0) > 0, ju

    print("Usage smoke OK:", usage)
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
