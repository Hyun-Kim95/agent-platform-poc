"""
LLM T2SQL smoke: needs LLM_API_KEY and RULES_ONLY=false.

Without a key, exits 0 with SKIP (so CI/offline stays green).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx

from app.core.config import get_settings

BASE = os.environ.get("AGENT_API_BASE", "http://127.0.0.1:8000")


def main() -> int:
    get_settings.cache_clear()
    settings = get_settings()
    if settings.rules_only or not (settings.llm_api_key or "").strip():
        print(
            "SKIP smoke_t2sql_llm: set LLM_API_KEY and RULES_ONLY=false"
        )
        return 0

    with httpx.Client(base_url=BASE, timeout=90.0) as client:
        r = client.post(
            "/v1/chat",
            json={
                "tenant_id": "internal",
                "engine": "hybrid_rag",
                "query": "product별 revenue 합계를 알려줘",
            },
        )
        r.raise_for_status()
        body = r.json()
        print(json.dumps(body, ensure_ascii=True, indent=2))

        assert body["status"] == "completed", body
        cites = body.get("citations") or []
        sql_cites = [c for c in cites if c.get("type") == "sql"]
        assert sql_cites, cites
        title = sql_cites[0].get("title") or ""
        assert (
            "(llm)" in title
            or "(template_fallback)" in title
            or "(template)" in title
        ), title

        usage = (body.get("meta") or {}).get("usage")
        if "(llm)" in title:
            assert usage is not None, body.get("meta")
            assert usage.get("estimated") is False, usage
            assert usage.get("total_tokens", 0) > 0, usage

    print("LLM T2SQL smoke OK")
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
