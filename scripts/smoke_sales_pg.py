"""Smoke sales backend: postgres if URL up, else sqlite."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.engines.hybrid_rag.db import active_backend, run_select
from app.engines.hybrid_rag.guardrail import check_sql


def main() -> int:
    cfg = get_settings()
    backend = active_backend(cfg)
    print("backend=", backend)

    sql = "SELECT SUM(revenue) AS total_revenue FROM sales LIMIT 1"
    ok, reason = check_sql(sql, settings=cfg)
    assert ok, reason
    cols, rows = run_select(sql, settings=cfg)
    print("cols=", cols, "rows=", rows)
    assert cols and rows
    total = float(rows[0][cols[0]])
    assert total > 0, rows
    print("smoke_sales_pg: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
