"""
TIMEOUT smoke: waiting_human then hitl after tenant timeout_ms.

Uses tenant=demo_timeout (hitl: true, timeout_ms: 1).
"""

from __future__ import annotations

import json
import os
import sys
import time

import httpx

BASE = os.environ.get("AGENT_API_BASE", "http://127.0.0.1:8000")
QUERY = "samples/mini.csv 기준 매출 합계를 알려줘."


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=60.0) as client:
        r = client.post(
            "/v1/chat",
            json={
                "tenant_id": "demo_timeout",
                "engine": "multi_agent",
                "query": QUERY,
            },
        )
        r.raise_for_status()
        body = r.json()
        print("chat:", json.dumps(body, ensure_ascii=True, indent=2))
        assert body["status"] == "waiting_human", body

        time.sleep(0.05)
        h = client.post(
            "/v1/hitl/{0}".format(body["run_id"]),
            json={"decision": "approve"},
        )
        h.raise_for_status()
        out = h.json()
        print("hitl:", json.dumps(out, ensure_ascii=True, indent=2))
        assert out["status"] == "failed", out
        assert out.get("error", {}).get("code") == "TIMEOUT", out

    print("TIMEOUT smoke OK")
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
