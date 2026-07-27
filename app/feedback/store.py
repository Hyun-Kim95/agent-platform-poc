"""Append-only feedback JSONL (D009)."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

_lock = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_feedback_id() -> str:
    return "fb_{0}".format(uuid.uuid4().hex)


class FeedbackStore:
    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)

    def append(
        self,
        *,
        run_id: str,
        rating: int,
        comment: Optional[str] = None,
        labels: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        record: Dict[str, Any] = {
            "feedback_id": new_feedback_id(),
            "run_id": run_id,
            "rating": rating,
            "comment": comment,
            "labels": list(labels or []),
            "stored_at": _utc_now(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False)
        with _lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line)
                f.write("\n")
        return record
