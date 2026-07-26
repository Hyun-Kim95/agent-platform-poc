"""
HITL demo: approve, revise, reject, 422, INVALID_HITL_STATE, 404.

Uses tenant=demo (hitl: true).
"""

from __future__ import annotations

import json
import os
import sys

import httpx

BASE = os.environ.get("AGENT_API_BASE", "http://127.0.0.1:8000")
QUERY = (
    "최근 AI 에이전트 관련 공개 기사 요지를 정리하고, "
    "samples/mini.csv 기준 매출 합계를 알려줘."
)


def _chat_waiting(client: httpx.Client) -> dict:
    r = client.post(
        "/v1/chat",
        json={
            "tenant_id": "demo",
            "engine": "multi_agent",
            "query": QUERY,
        },
    )
    r.raise_for_status()
    body = r.json()
    assert body["status"] == "waiting_human", body
    assert body.get("hitl") is not None, body
    return body


def _approve_flow(client: httpx.Client) -> str:
    body1 = _chat_waiting(client)
    print("chat1:", json.dumps(body1, ensure_ascii=True, indent=2))
    run_a = body1["run_id"]

    a = client.post(
        "/v1/hitl/{0}".format(run_a),
        json={"decision": "approve"},
    )
    a.raise_for_status()
    body_a = a.json()
    print("approve:", json.dumps(body_a, ensure_ascii=True, indent=2))
    assert body_a["status"] == "completed", body_a
    assert body_a["answer"], body_a
    return run_a


def _revise_flow(client: httpx.Client) -> None:
    body2 = _chat_waiting(client)
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
    assert body_rev["status"] == "waiting_human", body_rev
    assert body_rev["run_id"] == run_b, body_rev
    risks = (
        (body_rev.get("hitl") or {}).get("preview") or {}
    ).get("risks") or []
    assert any("human revise:" in str(x) for x in risks), body_rev

    a2 = client.post(
        "/v1/hitl/{0}".format(run_b),
        json={"decision": "approve"},
    )
    a2.raise_for_status()
    assert a2.json()["status"] == "completed", a2.json()


def _reject_flow(client: httpx.Client) -> None:
    body = _chat_waiting(client)
    run_c = body["run_id"]
    rej = client.post(
        "/v1/hitl/{0}".format(run_c),
        json={"decision": "reject"},
    )
    rej.raise_for_status()
    out = rej.json()
    assert out["status"] == "completed", out
    assert "Rejected" in (out.get("answer") or ""), out
    assert out.get("citations"), out


def _revise_without_feedback_422(client: httpx.Client) -> None:
    body = _chat_waiting(client)
    run_d = body["run_id"]
    bad = client.post(
        "/v1/hitl/{0}".format(run_d),
        json={"decision": "revise"},
    )
    assert bad.status_code == 422, bad.text
    # leave run waiting; approve to clean up
    client.post(
        "/v1/hitl/{0}".format(run_d),
        json={"decision": "approve"},
    ).raise_for_status()


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=120.0) as client:
        run_a = _approve_flow(client)
        _revise_flow(client)
        _reject_flow(client)
        _revise_without_feedback_422(client)

        again = client.post(
            "/v1/hitl/{0}".format(run_a),
            json={"decision": "approve"},
        )
        assert again.status_code == 200, again.text
        assert again.json()["error"]["code"] == "INVALID_HITL_STATE", again.json()

        missing = client.post(
            "/v1/hitl/run_does_not_exist",
            json={"decision": "approve"},
        )
        assert missing.status_code == 404, missing.text

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
