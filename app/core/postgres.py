"""Shared Postgres probe via VECTOR_DATABASE_URL."""

from __future__ import annotations

import logging
from typing import Optional

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def database_url(settings: Optional[Settings] = None) -> str:
    cfg = settings or get_settings()
    return (cfg.vector_database_url or "").strip()


def connect(url: str):
    import psycopg

    return psycopg.connect(url)


def postgres_available(settings: Optional[Settings] = None) -> bool:
    url = database_url(settings)
    if not url:
        return False
    try:
        with connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Postgres unavailable: %s", exc)
        return False
