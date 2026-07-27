"""
Feedback smoke — AC-F01, AC-F02, AC-F03.

Requires API up. Creates a real run via echo chat, then posts feedback.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

BASE = os.environ.get("AGENT_API_BASE", "http://127.0.0.1:8000")
FEEDBACK_JSONL = Path(
    os.environ.get("FEEDBACK_LOG_PATH", "data/feedback.jsonl")
)


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=30.0) as client:
        # seed run
        chat = client.post(
            "/v1/chat",
            json={
                "tenant_id": "internal",
                "engine": "echo",
                "query": "feedback smoke seed",
            },
        )
        chat.raise_for_status()
        run_id = chat.json()["run_id"]
        assert run_id, chat.json()

        before = (
            FEEDBACK_JSONL.stat().st_size if FEEDBACK_JSONL.is_file() else 0
        )

        # AC-F01
        ok = client.post(
            "/v1/feedback",
            json={
                "run_id": run_id,
                "rating": 5,
                "comment": "looks good",
                "labels": ["smoke"],
            },
        )
        assert ok.status_code == 200, ok.text
        body = ok.json()
        assert body.get("ok") is True, body
        assert body.get("feedback_id", "").startswith("fb_"), body
        assert body.get("run_id") == run_id, body
        assert body.get("stored_at"), body

        assert FEEDBACK_JSONL.is_file(), "feedback jsonl missing"
        raw = FEEDBACK_JSONL.read_bytes()
        chunk = (
            raw[before:].decode("utf-8")
            if before and before < len(raw)
            else raw.decode("utf-8")
        )
        lines = [ln for ln in chunk.strip().splitlines() if ln.strip()]
        assert lines, "no feedback lines"
        last = json.loads(lines[-1])
        assert last.get("feedback_id") == body["feedback_id"], last
        assert last.get("rating") == 5, last

        # AC-F02
        missing = client.post(
            "/v1/feedback",
            json={"run_id": "run_does_not_exist", "rating": 3},
        )
        assert missing.status_code == 404, missing.text
        err = missing.json()
        assert err.get("ok") is False, err
        assert err.get("error", {}).get("code") == "RUN_NOT_FOUND", err

        # AC-F03
        bad = client.post(
            "/v1/feedback",
            json={"run_id": run_id, "rating": 9},
        )
        assert bad.status_code == 422, bad.text

    print("Feedback smoke OK:", body)
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
