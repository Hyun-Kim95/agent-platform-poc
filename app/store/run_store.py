"""Disk-backed run store (Postgres or SQLite). Memory-only is forbidden."""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union

from app.core.config import Settings, get_settings
from app.core.postgres import connect as pg_connect
from app.core.postgres import database_url, postgres_available

logger = logging.getLogger(__name__)


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


# SQLite: graph_state stays TEXT (JSON string).
_DDL_SQLITE = """
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

# Postgres: graph_state is JSONB.
_DDL_POSTGRES = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    graph_state JSONB NOT NULL,
    tenant_id TEXT NOT NULL,
    engine TEXT NOT NULL,
    thread_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error_code TEXT
)
"""


def _parse_graph_state(raw: Any) -> Dict[str, Any]:
    """Accept dict (JSONB) or JSON string (TEXT / SQLite)."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
        raise TypeError("graph_state JSON must be an object")
    raise TypeError(
        "unsupported graph_state type: {0}".format(type(raw).__name__)
    )


class RunStore:
    def __init__(
        self,
        db_path: Union[str, Path, None] = None,
        *,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.path = Path(db_path or self.settings.run_store_path)
        self.backend = (
            "postgres" if postgres_available(self.settings) else "sqlite"
        )
        if self.backend == "postgres":
            self._init_postgres()
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._init_sqlite()

    def _init_sqlite(self) -> None:
        with self._connect_sqlite() as conn:
            conn.execute(_DDL_SQLITE)
            conn.commit()

    def _init_postgres(self) -> None:
        url = database_url(self.settings)
        with pg_connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute(_DDL_POSTGRES)
                self._ensure_graph_state_jsonb(cur)
            conn.commit()

    def _ensure_graph_state_jsonb(self, cur) -> None:
        """Migrate legacy TEXT graph_state → JSONB (no-op if already jsonb)."""
        cur.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'runs'
              AND column_name = 'graph_state'
            """
        )
        row = cur.fetchone()
        if row is None:
            return
        data_type = (row[0] or "").lower()
        if data_type in ("text", "character varying"):
            logger.info("migrating runs.graph_state %s -> jsonb", data_type)
            cur.execute(
                """
                ALTER TABLE runs
                ALTER COLUMN graph_state TYPE jsonb
                USING graph_state::jsonb
                """
            )

    def _connect_sqlite(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        return conn

    def save(self, record: RunRecord) -> None:
        if self.backend == "postgres":
            self._save_postgres(record)
        else:
            self._save_sqlite(record)

    def _save_sqlite(self, record: RunRecord) -> None:
        payload = (
            record.run_id,
            record.status,
            json.dumps(record.graph_state, ensure_ascii=False),
            record.tenant_id,
            record.engine,
            record.thread_id,
            record.created_at,
            record.updated_at,
            record.error_code,
        )
        with self._connect_sqlite() as conn:
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
                payload,
            )
            conn.commit()

    def _save_postgres(self, record: RunRecord) -> None:
        from psycopg.types.json import Json

        url = database_url(self.settings)
        payload = (
            record.run_id,
            record.status,
            Json(record.graph_state),
            record.tenant_id,
            record.engine,
            record.thread_id,
            record.created_at,
            record.updated_at,
            record.error_code,
        )
        with pg_connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO runs (
                        run_id, status, graph_state, tenant_id, engine,
                        thread_id, created_at, updated_at, error_code
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (run_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        graph_state = EXCLUDED.graph_state,
                        updated_at = EXCLUDED.updated_at,
                        error_code = EXCLUDED.error_code
                    """,
                    payload,
                )
            conn.commit()

    def get(self, run_id: str) -> Optional[RunRecord]:
        if self.backend == "postgres":
            return self._get_postgres(run_id)
        return self._get_sqlite(run_id)

    def _row_to_record(self, row: Any) -> RunRecord:
        if isinstance(row, dict):
            data = row
        else:
            data = dict(row)
        return RunRecord(
            run_id=data["run_id"],
            status=data["status"],
            graph_state=_parse_graph_state(data["graph_state"]),
            tenant_id=data["tenant_id"],
            engine=data["engine"],
            thread_id=data["thread_id"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            error_code=data["error_code"],
        )

    def _get_sqlite(self, run_id: str) -> Optional[RunRecord]:
        with self._connect_sqlite() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def _get_postgres(self, run_id: str) -> Optional[RunRecord]:
        url = database_url(self.settings)
        with pg_connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT run_id, status, graph_state, tenant_id, engine, "
                    "thread_id, created_at, updated_at, error_code "
                    "FROM runs WHERE run_id = %s",
                    (run_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                cols = [d[0] for d in cur.description]
                return self._row_to_record(dict(zip(cols, row)))

    @staticmethod
    def now() -> str:
        return _utc_now()
