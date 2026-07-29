"""
Router LLM fallback smoke: ambiguous query + LLM_API_KEY.

Without a key, exits 0 with SKIP.
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
            "SKIP smoke_router_llm: set LLM_API_KEY and RULES_ONLY=false"
        )
        return 0

    with httpx.Client(base_url=BASE, timeout=90.0) as client:
        # No RAG/SQL keywords -> rules would be both; LLM may refine.
        r = client.post(
            "/v1/chat",
            json={
                "tenant_id": "internal",
                "engine": "hybrid_rag",
                "query": "우리 서비스 소개를 짧게 정리해줘",
            },
        )
        r.raise_for_status()
        body = r.json()
        print("--- AMBIGUOUS ---")
        print(json.dumps(body, ensure_ascii=True, indent=2))
        assert body["status"] == "completed", body
        answer = body.get("answer") or ""
        assert "Route:" in answer, answer
        assert (
            "(llm)" in answer
            or "(rules_fallback)" in answer
            or "(rules)" in answer
        ), answer
        if "(llm)" in answer:
            usage = (body.get("meta") or {}).get("usage")
            assert usage is not None, body.get("meta")
            assert usage.get("total_tokens", 0) > 0, usage

        # Clear RAG keyword -> must stay rules (no router LLM).
        r2 = client.post(
            "/v1/chat",
            json={
                "tenant_id": "internal",
                "engine": "hybrid_rag",
                "query": "환불 정책 알려줘",
            },
        )
        r2.raise_for_status()
        clear = r2.json()
        print("--- CLEAR RAG ---")
        print(json.dumps(clear, ensure_ascii=True, indent=2))
        assert clear["status"] == "completed", clear
        assert clear["meta"]["route"] == "rag", clear["meta"]
        assert "Route: rag (rules)" in (clear.get("answer") or ""), clear.get(
            "answer"
        )

    print("Router LLM smoke OK")
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
