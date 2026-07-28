"""
Reviewer loop smoke: forced insufficiency hits max_iterations → MAX_ITERATIONS.

Uses tenant=demo_loop (hitl: false, max_iterations: 1).
"""

from __future__ import annotations

import json
import sys

import httpx

BASE = "http://127.0.0.1:8000"
QUERY = (
    "FORCE_INSUFFICIENT samples/mini.csv 기준 매출 합계와 "
    "관련 공개 기사 요지를 알려줘."
)


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=60.0) as client:
        r = client.post(
            "/v1/chat",
            json={
                "tenant_id": "demo_loop",
                "engine": "multi_agent",
                "query": QUERY,
            },
        )
        r.raise_for_status()
        body = r.json()
        print(json.dumps(body, ensure_ascii=True, indent=2))

        assert body["status"] == "failed", body
        assert body.get("error", {}).get("code") == "MAX_ITERATIONS", body
        assert body["meta"]["engine"] == "multi_agent", body["meta"]

    print("Reviewer loop smoke OK")
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
