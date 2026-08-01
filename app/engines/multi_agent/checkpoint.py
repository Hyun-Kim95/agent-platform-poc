"""Persistent LangGraph checkpointer: Postgres or SQLite fallback."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional

from app.core.config import Settings, get_settings
from app.core.postgres import database_url, postgres_available

logger = logging.getLogger(__name__)

_CHECKPOINTER: Any = None
_BACKEND: Optional[str] = None
_PG_POOL: Any = None
_SQLITE_CONN: Optional[sqlite3.Connection] = None


def checkpoint_backend() -> Optional[str]:
    return _BACKEND


def get_checkpointer(settings: Optional[Settings] = None) -> Any:
    """Return process-wide checkpointer (created once)."""
    global _CHECKPOINTER, _BACKEND, _PG_POOL, _SQLITE_CONN
    if _CHECKPOINTER is not None:
        return _CHECKPOINTER

    cfg = settings or get_settings()
    if postgres_available(cfg):
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
        from langgraph.checkpoint.postgres import PostgresSaver

        url = database_url(cfg)
        _PG_POOL = ConnectionPool(
            conninfo=url,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            },
            min_size=1,
            max_size=5,
            open=True,
        )
        saver = PostgresSaver(_PG_POOL)
        saver.setup()
        _CHECKPOINTER = saver
        _BACKEND = "postgres"
        logger.info("LangGraph checkpointer: postgres")
        return _CHECKPOINTER

    from langgraph.checkpoint.sqlite import SqliteSaver

    path = Path(cfg.checkpoint_sqlite_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _SQLITE_CONN = sqlite3.connect(str(path), check_same_thread=False)
    saver = SqliteSaver(_SQLITE_CONN)
    saver.setup()
    _CHECKPOINTER = saver
    _BACKEND = "sqlite"
    logger.info("LangGraph checkpointer: sqlite path=%s", path)
    return _CHECKPOINTER


def reset_checkpointer() -> None:
    """Close resources and clear singleton (tests / smoke)."""
    global _CHECKPOINTER, _BACKEND, _PG_POOL, _SQLITE_CONN
    if _PG_POOL is not None:
        try:
            _PG_POOL.close()
        except Exception:  # noqa: BLE001
            logger.warning("checkpoint pool close failed", exc_info=True)
        _PG_POOL = None
    if _SQLITE_CONN is not None:
        try:
            _SQLITE_CONN.close()
        except Exception:  # noqa: BLE001
            logger.warning("checkpoint sqlite close failed", exc_info=True)
        _SQLITE_CONN = None
    _CHECKPOINTER = None
    _BACKEND = None


def close_checkpointer() -> None:
    """Alias for app shutdown."""
    reset_checkpointer()
