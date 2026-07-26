"""
HITL demo: waiting_human -> approve, and waiting_human -> revise once.

Uses tenant=demo (hitl: true).
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
    with httpx.Client(base_url=BASE, timeout=120.0) as client:
        # --- approve path ---
        r1 = client.post(
            "/v1/chat",
            json={
                "tenant_id": "demo",
                "engine": "multi_agent",
                "query": QUERY,
            },
        )
        r1.raise_for_status()
        body1 = r1.json()
        print("chat1:", json.dumps(body1, ensure_ascii=True, indent=2))
        assert body1["status"] == "waiting_human", body1
        assert body1.get("hitl") is not None
        run_a = body1["run_id"]

        a = client.post(
            "/v1/hitl/{0}".format(run_a),
            json={"decision": "approve"},
        )
        a.raise_for_status()
        body_a = a.json()
        print("approve:", json.dumps(body_a, ensure_ascii=True, indent=2))
        assert body_a["status"] == "completed"
        assert body_a["answer"]

        # --- revise path ---
        r2 = client.post(
            "/v1/chat",
            json={
                "tenant_id": "demo",
                "engine": "multi_agent",
                "query": QUERY,
            },
        )
        r2.raise_for_status()
        body2 = r2.json()
        assert body2["status"] == "waiting_human"
        run_b = body2["run_id"]

        rev = client.post(
            "/v1/hitl/{0}".format(run_b),
            json={
                "decision": "revise",
                "feedback": "Prefer more reliable domains",
                "revise_target": "search",
            },
        )
        rev.raise_for_status()
        body_rev = rev.json()
        print("revise:", json.dumps(body_rev, ensure_ascii=True, indent=2))
        assert body_rev["status"] == "waiting_human"
        assert body_rev["run_id"] == run_b

        a2 = client.post(
            "/v1/hitl/{0}".format(run_b),
            json={"decision": "approve"},
        )
        a2.raise_for_status()
        assert a2.json()["status"] == "completed"

        # invalid state
        again = client.post(
            "/v1/hitl/{0}".format(run_a),
            json={"decision": "approve"},
        )
        assert again.status_code == 200
        assert again.json()["error"]["code"] == "INVALID_HITL_STATE"

        missing = client.post(
            "/v1/hitl/run_does_not_exist",
            json={"decision": "approve"},
        )
        assert missing.status_code == 404

    print("HITL demo OK")
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
