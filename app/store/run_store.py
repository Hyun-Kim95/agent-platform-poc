"""Disk-backed run store (SQLite). Memory-only is forbidden."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class RunRecord:
    run_id: str
    status: str
    graph_state: Dict[str, Any]
    tenant_id: str
    engine: str
    thread_id: Optional[str]
    created_at: str
    updated_at: str
    error_code: Optional[str] = None


class RunStore:
    def __init__(self, db_path: Union[str, Path]) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    graph_state TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    thread_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error_code TEXT
                )
                """
            )
            conn.commit()

    def save(self, record: RunRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    run_id, status, graph_state, tenant_id, engine,
                    thread_id, created_at, updated_at, error_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status=excluded.status,
                    graph_state=excluded.graph_state,
                    updated_at=excluded.updated_at,
                    error_code=excluded.error_code
                """,
                (
                    record.run_id,
                    record.status,
                    json.dumps(record.graph_state, ensure_ascii=False),
                    record.tenant_id,
                    record.engine,
                    record.thread_id,
                    record.created_at,
                    record.updated_at,
                    record.error_code,
                ),
            )
            conn.commit()

    def get(self, run_id: str) -> Optional[RunRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        return RunRecord(
            run_id=row["run_id"],
            status=row["status"],
            graph_state=json.loads(row["graph_state"]),
            tenant_id=row["tenant_id"],
            engine=row["engine"],
            thread_id=row["thread_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            error_code=row["error_code"],
        )

    @staticmethod
    def now() -> str:
        return _utc_now()
