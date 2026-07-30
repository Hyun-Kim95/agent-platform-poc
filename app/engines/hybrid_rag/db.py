"""Hybrid sales DB: Postgres when VECTOR_DATABASE_URL works, else SQLite."""

from __future__ import annotations

import csv
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB = ROOT / "samples" / "hybrid.db"
DEFAULT_CSV = ROOT / "samples" / "mini.csv"


def _load_csv_rows(csv_path: Path) -> List[Tuple[str, str, float]]:
    if not csv_path.is_file():
        return []
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return [
            (
                row.get("date") or "",
                row.get("product") or "",
                float(row.get("revenue") or 0),
            )
            for row in reader
        ]


def _normalize_sql(sql: str) -> str:
    return (sql or "").strip().rstrip(";").strip()


def _pg_connect(url: str):
    import psycopg

    return psycopg.connect(url)


def postgres_available(settings: Optional[Settings] = None) -> bool:
    cfg = settings or get_settings()
    url = (cfg.vector_database_url or "").strip()
    if not url:
        return False
    try:
        with _pg_connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("sales Postgres unavailable: %s", exc)
        return False


def active_backend(settings: Optional[Settings] = None) -> str:
    """Return 'postgres' or 'sqlite'."""
    return "postgres" if postgres_available(settings) else "sqlite"


def ensure_hybrid_db(
    db_path: Path = DEFAULT_DB,
    csv_path: Path = DEFAULT_CSV,
) -> Path:
    """SQLite bootstrap (fallback path)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS sales ("
            "date TEXT, product TEXT, revenue REAL)"
        )
        n = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
        if int(n) == 0:
            rows = _load_csv_rows(csv_path)
            if rows:
                conn.executemany(
                    "INSERT INTO sales(date, product, revenue) VALUES (?,?,?)",
                    rows,
                )
                conn.commit()
    finally:
        conn.close()
    return db_path


def ensure_sales_postgres(settings: Optional[Settings] = None) -> None:
    cfg = settings or get_settings()
    url = (cfg.vector_database_url or "").strip()
    if not url:
        raise RuntimeError("VECTOR_DATABASE_URL is empty")
    rows = _load_csv_rows(DEFAULT_CSV)
    with _pg_connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS sales (
                    date TEXT,
                    product TEXT,
                    revenue DOUBLE PRECISION
                )
                """
            )
            cur.execute("SELECT COUNT(*) FROM sales")
            n = int(cur.fetchone()[0])
            if n == 0 and rows:
                cur.executemany(
                    "INSERT INTO sales(date, product, revenue) VALUES (%s, %s, %s)",
                    rows,
                )
        conn.commit()


def _run_select_sqlite(
    sql: str,
    db_path: Path = DEFAULT_DB,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    ensure_hybrid_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(_normalize_sql(sql))
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [dict(r) for r in cur.fetchall()]
        return cols, rows
    finally:
        conn.close()


def _run_select_postgres(
    sql: str,
    settings: Optional[Settings] = None,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    cfg = settings or get_settings()
    ensure_sales_postgres(cfg)
    url = (cfg.vector_database_url or "").strip()
    with _pg_connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(_normalize_sql(sql))
            cols = [d[0] for d in cur.description] if cur.description else []
            raw = cur.fetchall()
            rows = [dict(zip(cols, row)) for row in raw]
            return cols, rows


def run_select(
    sql: str,
    db_path: Path = DEFAULT_DB,
    *,
    settings: Optional[Settings] = None,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    cfg = settings or get_settings()
    if postgres_available(cfg):
        return _run_select_postgres(sql, settings=cfg)
    return _run_select_sqlite(sql, db_path=db_path)
