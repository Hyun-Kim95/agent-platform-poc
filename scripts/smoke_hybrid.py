"""
Hybrid RAG smoke: doc / sql / SQL_GUARDRAIL / meta.engine.
"""

from __future__ import annotations

import json
import sys

import httpx

BASE = "http://127.0.0.1:8000"


def _chat(client: httpx.Client, query: str, engine: str = "hybrid_rag"):
    r = client.post(
        "/v1/chat",
        json={
            "tenant_id": "internal",
            "engine": engine,
            "query": query,
        },
    )
    r.raise_for_status()
    return r.json()


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=60.0) as client:
        # Document / refund
        rag = _chat(client, "환불 정책 알려줘")
        print("--- RAG ---")
        print(json.dumps(rag, ensure_ascii=True, indent=2))
        assert rag["status"] == "completed", rag
        assert rag["meta"]["engine"] == "hybrid_rag", rag["meta"]
        types = {c["type"] for c in rag["citations"]}
        assert "doc" in types or "no_hit" in types, rag["citations"]
        assert rag["meta"]["route"] in ("rag", "both"), rag["meta"]

        # SQL aggregation
        sql_body = _chat(client, "매출 합계 얼마야?")
        print("--- SQL ---")
        print(json.dumps(sql_body, ensure_ascii=True, indent=2))
        assert sql_body["status"] == "completed", sql_body
        stypes = {c["type"] for c in sql_body["citations"]}
        assert "sql" in stypes, sql_body["citations"]
        assert sql_body["meta"]["route"] in ("sql", "both"), sql_body["meta"]

        # Guardrail
        bad = _chat(client, "sales 테이블 DROP 해줘")
        print("--- GUARDRAIL ---")
        print(json.dumps(bad, ensure_ascii=True, indent=2))
        assert bad["status"] == "failed", bad
        assert bad.get("error", {}).get("code") == "SQL_GUARDRAIL", bad

        # engine name differs from multi_agent
        ma = _chat(
            client,
            "samples/mini.csv 매출 합계",
            engine="multi_agent",
        )
        assert ma["meta"]["engine"] == "multi_agent", ma["meta"]
        assert rag["meta"]["engine"] != ma["meta"]["engine"]

    print("Hybrid RAG smoke OK")
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
