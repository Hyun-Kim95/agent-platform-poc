"""SQLite hybrid DB: bootstrap from samples/mini.csv."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB = ROOT / "samples" / "hybrid.db"
DEFAULT_CSV = ROOT / "samples" / "mini.csv"


def ensure_hybrid_db(
    db_path: Path = DEFAULT_DB,
    csv_path: Path = DEFAULT_CSV,
) -> Path:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS sales ("
            "date TEXT, product TEXT, revenue REAL)"
        )
        n = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
        if int(n) == 0 and csv_path.is_file():
            with csv_path.open(encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                rows = [
                    (
                        row.get("date") or "",
                        row.get("product") or "",
                        float(row.get("revenue") or 0),
                    )
                    for row in reader
                ]
            conn.executemany(
                "INSERT INTO sales(date, product, revenue) VALUES (?,?,?)",
                rows,
            )
            conn.commit()
    finally:
        conn.close()
    return db_path


def run_select(
    sql: str,
    db_path: Path = DEFAULT_DB,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    ensure_hybrid_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [dict(r) for r in cur.fetchall()]
        return cols, rows
    finally:
        conn.close()
