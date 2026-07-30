"""Unit smoke for sqlparse + sqlglot Guardrail (no HTTP)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.engines.hybrid_rag.guardrail import check_sql


def expect(ok: bool, sql: str, label: str) -> None:
    got_ok, reason = check_sql(sql)
    if got_ok != ok:
        raise AssertionError(
            "{0}: expected ok={1}, got ok={2}, reason={3!r}, sql={4!r}".format(
                label, ok, got_ok, reason, sql
            )
        )
    print("OK  {0}  (ok={1}, reason={2!r})".format(label, got_ok, reason))


def main() -> None:
    # L3: comments
    expect(
        True,
        "SELECT region, SUM(revenue) AS total FROM sales "
        "GROUP BY region LIMIT 10 -- DROP TABLE sales",
        "comment-with-DROP",
    )
    expect(
        True,
        "SELECT * FROM sales /* DROP TABLE sales */ LIMIT 5",
        "block-comment-with-DROP",
    )

    # L3 basics
    expect(False, "DROP TABLE sales", "real-DROP")
    expect(False, "SELECT * FROM sales", "no-LIMIT")
    expect(False, "SELECT * FROM orders LIMIT 1", "bad-table")
    expect(False, "SELECT 1; SELECT 2", "multi-statement")
    expect(
        False,
        "SELECT * FROM sales; DROP TABLE sales",
        "select-then-DROP",
    )

    # Happy path with allowlisted agg
    expect(
        True,
        "SELECT SUM(revenue) AS total_revenue FROM sales LIMIT 1",
        "sum-ok",
    )

    # P2 AST
    expect(
        False,
        "SELECT * FROM (SELECT * FROM orders) t LIMIT 1",
        "subquery-orders",
    )
    expect(
        False,
        "SELECT a FROM sales UNION SELECT b FROM sales LIMIT 1",
        "union",
    )
    expect(
        False,
        "SELECT SLEEP(1) FROM sales LIMIT 1",
        "bad-function",
    )

    print("smoke_guardrail: all passed")


if __name__ == "__main__":
    main()
