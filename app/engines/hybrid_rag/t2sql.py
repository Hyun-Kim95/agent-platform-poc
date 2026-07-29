"""Text-to-SQL: template always; optional LLM when key + not rules_only."""

from __future__ import annotations

import re
from typing import Optional, Tuple

from app.core.config import Settings, get_settings
from app.core.models import TokenUsage
from app.llm.client import LlmError, chat_completion

_DANGEROUS = (
    "drop",
    "delete",
    "update",
    "insert",
    "truncate",
    "alter",
)

_SCHEMA_HINT = (
    "SQLite table sales(date TEXT, product TEXT, revenue REAL). "
    "Only this table is allowed."
)

_SYSTEM = (
    "You write one SQLite SELECT for analytics. "
    "Rules: SELECT only; table sales only; must include LIMIT; "
    "no DDL/DML; no multiple statements; no markdown. "
    "Reply with SQL only."
)


def generate_sql_template(query: str) -> str:
    q = query or ""
    lower = q.lower()

    # Word-boundary only (avoid substring false positives like "updated").
    for word in _DANGEROUS:
        if re.search(r"\b" + word + r"\b", lower):
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


def _extract_sql(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""

    fence = re.search(
        r"```(?:sql)?\s*([\s\S]*?)```",
        raw,
        flags=re.IGNORECASE,
    )
    if fence:
        raw = fence.group(1).strip()

    for line in raw.splitlines():
        s = line.strip().rstrip(";")
        if s.lower().startswith("select"):
            return s + ";"

    if raw.lower().lstrip().startswith("select"):
        return raw.rstrip().rstrip(";") + ";"
    return ""


def generate_sql(
    query: str,
    *,
    rules_only: bool = False,
    settings: Optional[Settings] = None,
) -> Tuple[str, Optional[TokenUsage], str]:
    """Return (sql, llm_usage_or_none, source)."""
    cfg = settings or get_settings()
    template = generate_sql_template(query)

    if template.upper().startswith("DROP"):
        return template, None, "template"

    use_llm = (
        not rules_only
        and bool((cfg.llm_api_key or "").strip())
    )
    if not use_llm:
        return template, None, "template"

    messages = [
        {"role": "system", "content": _SYSTEM + " " + _SCHEMA_HINT},
        {
            "role": "user",
            "content": "Question: {0}".format(query or ""),
        },
    ]
    try:
        text, usage = chat_completion(messages, settings=cfg, temperature=0.0)
    except LlmError:
        return template, None, "template_fallback"

    sql = _extract_sql(text)
    if not sql:
        return template, None, "template_fallback"

    return sql, usage, "llm"
