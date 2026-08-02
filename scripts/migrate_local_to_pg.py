"""One-shot copy: local SQLite runs + JSONL feedback -> shared Postgres.

Does not change runtime fallbacks. Sales/docs/checkpoints are out of scope.

Examples:
  python scripts/migrate_local_to_pg.py --dry-run
  python scripts/migrate_local_to_pg.py
  python scripts/migrate_local_to_pg.py --only runs --on-conflict overwrite
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from psycopg.types.json import Json

from app.core.config import get_settings
from app.core.postgres import connect as pg_connect
from app.core.postgres import database_url, postgres_available
from app.feedback.store import _DDL as FEEDBACK_DDL
from app.store.run_store import (
    _DDL_POSTGRES as RUNS_DDL,
    _parse_graph_state,
)


def _read_runs_sqlite(path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    rows: List[Dict[str, Any]] = []
    errors: List[str] = []
    if not path.is_file():
        return rows, errors
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        try:
            cur = conn.execute(
                "SELECT run_id, status, graph_state, tenant_id, engine, "
                "thread_id, created_at, updated_at, error_code FROM runs"
            )
        except sqlite3.OperationalError as exc:
            errors.append("runs table missing or unreadable: {0}".format(exc))
            return rows, errors
        for raw in cur.fetchall():
            data = dict(raw)
            rid = data.get("run_id") or "?"
            try:
                data["graph_state"] = _parse_graph_state(data.get("graph_state"))
            except (TypeError, json.JSONDecodeError, ValueError) as exc:
                errors.append(
                    "skip run_id={0}: bad graph_state ({1})".format(rid, exc)
                )
                continue
            rows.append(data)
    finally:
        conn.close()
    return rows, errors


def _read_feedback_jsonl(
    path: Path,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    rows: List[Dict[str, Any]] = []
    errors: List[str] = []
    if not path.is_file():
        return rows, errors
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(
                    "skip feedback line {0}: {1}".format(lineno, exc)
                )
                continue
            if not isinstance(obj, dict):
                errors.append(
                    "skip feedback line {0}: not an object".format(lineno)
                )
                continue
            fid = obj.get("feedback_id")
            if not fid or not obj.get("run_id"):
                errors.append(
                    "skip feedback line {0}: missing feedback_id/run_id".format(
                        lineno
                    )
                )
                continue
            try:
                rating = int(obj["rating"])
            except (KeyError, TypeError, ValueError):
                errors.append(
                    "skip feedback_id={0}: bad rating".format(fid)
                )
                continue
            labels = obj.get("labels") or []
            if isinstance(labels, str):
                try:
                    labels = json.loads(labels)
                except json.JSONDecodeError:
                    labels = []
            if not isinstance(labels, list):
                labels = []
            rows.append(
                {
                    "feedback_id": str(fid),
                    "run_id": str(obj["run_id"]),
                    "rating": rating,
                    "comment": obj.get("comment"),
                    "labels": labels,
                    "stored_at": obj.get("stored_at") or "",
                }
            )
    return rows, errors


def _pg_existing_ids(cur, table: str, id_col: str) -> set:
    cur.execute("SELECT {0} FROM {1}".format(id_col, table))
    return {r[0] for r in cur.fetchall()}


def _migrate_runs(
    cur,
    rows: List[Dict[str, Any]],
    *,
    dry_run: bool,
    on_conflict: str,
) -> Dict[str, int]:
    existing = _pg_existing_ids(cur, "runs", "run_id")
    inserted = 0
    skipped = 0
    updated = 0
    sql_skip = """
        INSERT INTO runs (
            run_id, status, graph_state, tenant_id, engine,
            thread_id, created_at, updated_at, error_code
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (run_id) DO NOTHING
    """
    sql_upsert = """
        INSERT INTO runs (
            run_id, status, graph_state, tenant_id, engine,
            thread_id, created_at, updated_at, error_code
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (run_id) DO UPDATE SET
            status = EXCLUDED.status,
            graph_state = EXCLUDED.graph_state,
            tenant_id = EXCLUDED.tenant_id,
            engine = EXCLUDED.engine,
            thread_id = EXCLUDED.thread_id,
            created_at = EXCLUDED.created_at,
            updated_at = EXCLUDED.updated_at,
            error_code = EXCLUDED.error_code
    """
    for row in rows:
        rid = row["run_id"]
        exists = rid in existing
        if exists and on_conflict == "skip":
            skipped += 1
            continue
        if dry_run:
            if exists:
                updated += 1
            else:
                inserted += 1
            continue
        payload = (
            row["run_id"],
            row["status"],
            Json(row["graph_state"]),
            row["tenant_id"],
            row["engine"],
            row["thread_id"],
            row["created_at"],
            row["updated_at"],
            row["error_code"],
        )
        if on_conflict == "overwrite":
            cur.execute(sql_upsert, payload)
            if exists:
                updated += 1
            else:
                inserted += 1
                existing.add(rid)
        else:
            cur.execute(sql_skip, payload)
            if cur.rowcount:
                inserted += 1
                existing.add(rid)
            else:
                skipped += 1
    return {"inserted": inserted, "skipped": skipped, "updated": updated}


def _migrate_feedback(
    cur,
    rows: List[Dict[str, Any]],
    *,
    dry_run: bool,
    on_conflict: str,
) -> Dict[str, int]:
    existing = _pg_existing_ids(cur, "feedback", "feedback_id")
    inserted = 0
    skipped = 0
    updated = 0
    sql_skip = """
        INSERT INTO feedback (
            feedback_id, run_id, rating, comment, labels, stored_at
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (feedback_id) DO NOTHING
    """
    sql_upsert = """
        INSERT INTO feedback (
            feedback_id, run_id, rating, comment, labels, stored_at
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (feedback_id) DO UPDATE SET
            run_id = EXCLUDED.run_id,
            rating = EXCLUDED.rating,
            comment = EXCLUDED.comment,
            labels = EXCLUDED.labels,
            stored_at = EXCLUDED.stored_at
    """
    for row in rows:
        fid = row["feedback_id"]
        exists = fid in existing
        if exists and on_conflict == "skip":
            skipped += 1
            continue
        if dry_run:
            if exists:
                updated += 1
            else:
                inserted += 1
            continue
        payload = (
            row["feedback_id"],
            row["run_id"],
            row["rating"],
            row["comment"],
            Json(row["labels"]),
            row["stored_at"],
        )
        if on_conflict == "overwrite":
            cur.execute(sql_upsert, payload)
            if exists:
                updated += 1
            else:
                inserted += 1
                existing.add(fid)
        else:
            cur.execute(sql_skip, payload)
            if cur.rowcount:
                inserted += 1
                existing.add(fid)
            else:
                skipped += 1
    return {"inserted": inserted, "skipped": skipped, "updated": updated}


def main(argv: Optional[List[str]] = None) -> int:
    cfg = get_settings()
    parser = argparse.ArgumentParser(
        description="Migrate local runs.db + feedback.jsonl to Postgres"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count only; do not INSERT",
    )
    parser.add_argument(
        "--runs-db",
        type=Path,
        default=Path(cfg.run_store_path),
        help="Source SQLite path (default: RUN_STORE_PATH)",
    )
    parser.add_argument(
        "--feedback-jsonl",
        type=Path,
        default=Path(cfg.feedback_log_path),
        help="Source JSONL path (default: FEEDBACK_LOG_PATH)",
    )
    parser.add_argument(
        "--only",
        choices=("all", "runs", "feedback"),
        default="all",
    )
    parser.add_argument(
        "--on-conflict",
        choices=("skip", "overwrite"),
        default="skip",
        help="skip=keep PG row (default); overwrite=UPSERT",
    )
    args = parser.parse_args(argv)

    if not postgres_available(cfg):
        print(
            "ERROR: Postgres unavailable. Set VECTOR_DATABASE_URL "
            "and start docker compose.",
            file=sys.stderr,
        )
        return 1

    url = database_url(cfg)
    print("target=", url.split("@")[-1] if "@" in url else "(url)")
    print("dry_run=", args.dry_run, "on_conflict=", args.on_conflict)

    do_runs = args.only in ("all", "runs")
    do_fb = args.only in ("all", "feedback")

    run_rows: List[Dict[str, Any]] = []
    fb_rows: List[Dict[str, Any]] = []
    if do_runs:
        print("source runs=", args.runs_db)
        run_rows, run_errs = _read_runs_sqlite(args.runs_db)
        for msg in run_errs:
            print("WARN", msg)
        print("source runs count=", len(run_rows))
    if do_fb:
        print("source feedback=", args.feedback_jsonl)
        fb_rows, fb_errs = _read_feedback_jsonl(args.feedback_jsonl)
        for msg in fb_errs:
            print("WARN", msg)
        print("source feedback count=", len(fb_rows))

    with pg_connect(url) as conn:
        with conn.cursor() as cur:
            if not args.dry_run:
                cur.execute(RUNS_DDL)
                cur.execute(FEEDBACK_DDL)
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
                if row is not None and (row[0] or "").lower() in (
                    "text",
                    "character varying",
                ):
                    cur.execute(
                        """
                        ALTER TABLE runs
                        ALTER COLUMN graph_state TYPE jsonb
                        USING graph_state::jsonb
                        """
                    )
            if do_runs:
                stats = _migrate_runs(
                    cur,
                    run_rows,
                    dry_run=args.dry_run,
                    on_conflict=args.on_conflict,
                )
                print(
                    "runs inserted={0} skipped={1} updated={2}".format(
                        stats["inserted"],
                        stats["skipped"],
                        stats["updated"],
                    )
                )
            if do_fb:
                stats = _migrate_feedback(
                    cur,
                    fb_rows,
                    dry_run=args.dry_run,
                    on_conflict=args.on_conflict,
                )
                print(
                    "feedback inserted={0} skipped={1} updated={2}".format(
                        stats["inserted"],
                        stats["skipped"],
                        stats["updated"],
                    )
                )
        if not args.dry_run:
            conn.commit()

    print("migrate_local_to_pg: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
