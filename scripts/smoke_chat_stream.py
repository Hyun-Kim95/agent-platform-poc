"""Smoke POST /v1/chat/stream (SSE)."""

from __future__ import annotations

import json
import os
import sys

import httpx

BASE = os.environ.get("AGENT_API_BASE", "http://127.0.0.1:8000")


def main() -> int:
    url = BASE.rstrip("/") + "/v1/chat/stream"
    body = {
        "tenant_id": "internal",
        "engine": "echo",
        "query": "stream smoke",
    }
    events = []
    with httpx.Client(timeout=60.0) as client:
        try:
            with client.stream("POST", url, json=body) as res:
                if res.status_code != 200:
                    print("FAIL status", res.status_code, res.read())
                    return 1
                buf = ""
                for chunk in res.iter_text():
                    buf += chunk
                    while "\n\n" in buf:
                        frame, buf = buf.split("\n\n", 1)
                        ev = None
                        data = None
                        for line in frame.splitlines():
                            if line.startswith("event:"):
                                ev = line[6:].strip()
                            elif line.startswith("data:"):
                                data = json.loads(line[5:].strip())
                        if ev:
                            events.append((ev, data))
                            if ev == "envelope":
                                print(
                                    "event",
                                    ev,
                                    "{status=%s}" % (data or {}).get("status"),
                                )
                            else:
                                print("event", ev, data)
        except httpx.ConnectError:
            print("ERROR: API not running at", BASE)
            return 1

    names = [e for e, _ in events]
    if "run" not in names or "envelope" not in names or "done" not in names:
        print("FAIL missing events", names)
        return 1
    if "phase" not in names:
        print("FAIL no phase", names)
        return 1
    print("smoke_chat_stream: ok", names)
    return 0


if __name__ == "__main__":
    sys.exit(main())
