"""
Smoke: Registry branching via echo vs multi_agent.

Checks that meta.engine differs between engines, plus /health and
TENANT_NOT_FOUND / ENGINE_NOT_FOUND (HTTP 200 + status=failed).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000"


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=30.0) as client:
        h = client.get("/health")
        h.raise_for_status()
        assert h.json().get("ok") is True, h.text
        print("OK /health", h.json())

        # echo engine
        echo = client.post(
            "/v1/chat",
            json={
                "tenant_id": "demo",
                "engine": "echo",
                "query": "hello registry",
            },
        )
        echo.raise_for_status()
        echo_body = echo.json()
        print("echo:", json.dumps(echo_body, ensure_ascii=True, indent=2))
        assert echo_body["status"] == "completed"
        assert echo_body["meta"]["engine"] == "echo", echo_body["meta"]
        assert echo_body["answer"] and echo_body["answer"].startswith("[echo]")

        # multi_agent engine (meta.engine must differ from echo)
        ma = client.post(
            "/v1/chat",
            json={
                "tenant_id": "demo",
                "engine": "multi_agent",
                "query": "hello registry",
            },
        )
        ma.raise_for_status()
        ma_body = ma.json()
        print("multi_agent:", json.dumps(ma_body, ensure_ascii=True, indent=2))
        assert ma_body["meta"]["engine"] == "multi_agent"
        assert ma_body["meta"]["engine"] != echo_body["meta"]["engine"]

        # Domain errors stay HTTP 200
        bad_tenant = client.post(
            "/v1/chat",
            json={"tenant_id": "nope", "engine": "echo", "query": "x"},
        )
        assert bad_tenant.status_code == 200
        assert bad_tenant.json()["status"] == "failed"
        assert bad_tenant.json()["error"]["code"] == "TENANT_NOT_FOUND"

        bad_engine = client.post(
            "/v1/chat",
            json={
                "tenant_id": "demo",
                "engine": "does_not_exist",
                "query": "x",
            },
        )
        assert bad_engine.status_code == 200
        assert bad_engine.json()["error"]["code"] == "ENGINE_NOT_FOUND"

    print("Registry smoke OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except httpx.ConnectError:
        print(
            "ERROR: API not running. Start with:\n"
            "  uvicorn app.main:app --port 8000",
            file=sys.stderr,
        )
        raise SystemExit(1)
