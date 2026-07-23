"""
Smoke: mixed web+CSV question without HITL.

Uses tenant=internal (hitl: false).
Expect: completed, meta.engine=multi_agent, route set, citations present.
"""

from __future__ import annotations

import json
import sys

import httpx

BASE = "http://127.0.0.1:8000"
QUERY = (
    "최근 AI 에이전트 관련 공개 기사 요지를 정리하고, "
    "samples/mini.csv 기준 매출 합계를 알려줘."
)


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=60.0) as client:
        r = client.post(
            "/v1/chat",
            json={
                "tenant_id": "internal",
                "engine": "multi_agent",
                "query": QUERY,
            },
        )
        r.raise_for_status()
        body = r.json()
        print(json.dumps(body, ensure_ascii=True, indent=2))

        assert body["status"] == "completed", body
        assert body["meta"]["engine"] == "multi_agent", body["meta"]
        assert body["answer"], "empty answer"
        assert body["meta"].get("route") in ("web", "data", "both", "clarify")
        types = {c["type"] for c in body.get("citations") or []}
        assert types & {"web", "data", "no_hit"}, types

    print("Mixed-question smoke OK")
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
