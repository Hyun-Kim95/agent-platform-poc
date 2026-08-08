"""SSE frame helpers for POST /v1/chat/stream."""

from __future__ import annotations

import json
from typing import Any, Dict


def format_sse(event: str, data: Dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return "event: {0}\ndata: {1}\n\n".format(event, payload)
