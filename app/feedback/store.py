"""Append-only feedback: Postgres or JSONL fallback."""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from app.core.config import Settings, get_settings
from app.core.postgres import connect as pg_connect
from app.core.postgres import database_url, postgres_available

_lock = threading.Lock()
_logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    rating INTEGER NOT NULL,
    comment TEXT,
    labels JSONB NOT NULL DEFAULT '[]'::jsonb,
    stored_at TEXT NOT NULL
)
"""


class FeedbackAppendError(Exception):
    """Disk/IO failure while appending feedback (maps to INTERNAL)."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_feedback_id() -> str:
    return "fb_{0}".format(uuid.uuid4().hex)


class FeedbackStore:
    def __init__(
        self,
        path: Union[str, Path, None] = None,
        *,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.path = Path(path or self.settings.feedback_log_path)
        self.backend = (
            "postgres" if postgres_available(self.settings) else "jsonl"
        )
        if self.backend == "postgres":
            self._init_postgres()
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def _init_postgres(self) -> None:
        url = database_url(self.settings)
        with pg_connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute(_DDL)
            conn.commit()

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
        try:
            if self.backend == "postgres":
                self._append_postgres(record)
            else:
                self._append_jsonl(record)
        except FeedbackAppendError:
            raise
        except Exception as exc:
            _logger.warning(
                "feedback append failed backend=%s path=%s",
                self.backend,
                self.path,
                exc_info=True,
            )
            raise FeedbackAppendError(
                "failed to append feedback ({0})".format(self.backend)
            ) from exc
        return record

    def _append_jsonl(self, record: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False)
        with _lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line)
                f.write("\n")

    def _append_postgres(self, record: Dict[str, Any]) -> None:
        from psycopg.types.json import Json

        url = database_url(self.settings)
        with pg_connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO feedback (
                        feedback_id, run_id, rating, comment, labels, stored_at
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record["feedback_id"],
                        record["run_id"],
                        record["rating"],
                        record["comment"],
                        Json(record["labels"]),
                        record["stored_at"],
                    ),
                )
            conn.commit()

    def get(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        """Lookup for smoke/debug. None if missing."""
        if self.backend == "postgres":
            return self._get_postgres(feedback_id)
        return self._get_jsonl(feedback_id)

    def _get_postgres(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        url = database_url(self.settings)
        with pg_connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT feedback_id, run_id, rating, comment, labels, "
                    "stored_at FROM feedback WHERE feedback_id = %s",
                    (feedback_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                cols = [d[0] for d in cur.description]
                data = dict(zip(cols, row))
                labels = data.get("labels")
                if isinstance(labels, str):
                    labels = json.loads(labels)
                data["labels"] = list(labels or [])
                return data

    def _get_jsonl(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        if not self.path.is_file():
            return None
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("feedback_id") == feedback_id:
                    return obj
        return None
