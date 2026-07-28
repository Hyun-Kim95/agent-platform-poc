"""Rule-first text-to-SQL (template). Dangerous intents emit bad SQL for Guardrail."""

from __future__ import annotations

import re

_DANGEROUS = (
    "drop",
    "delete",
    "update",
    "insert",
    "truncate",
    "alter",
)


def generate_sql(query: str) -> str:
    q = query or ""
    lower = q.lower()

    for word in _DANGEROUS:
        if re.search(r"\b" + word + r"\b", lower) or word in q.lower():
            # Intentional unsafe candidate so Guardrail can refuse (H03).
            return "DROP TABLE sales;"

    if any(k in q for k in ("합계", "매출", "revenue", "sum", "총")):
        return (
            "SELECT SUM(revenue) AS revenue_sum "
            "FROM sales LIMIT 100"
        )

    if any(k in lower for k in ("product", "상품", "제품")):
        return (
            "SELECT product, SUM(revenue) AS revenue_sum "
            "FROM sales GROUP BY product LIMIT 100"
        )

    return (
        "SELECT date, product, revenue "
        "FROM sales ORDER BY date LIMIT 20"
    )
