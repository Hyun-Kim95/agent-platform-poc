"""T2SQL Guardrail: SELECT-only, table allowlist, LIMIT required."""

from __future__ import annotations

import re
from typing import Optional, Tuple

ALLOWED_TABLES = frozenset({"sales"})
FORBIDDEN = (
    "drop",
    "delete",
    "update",
    "insert",
    "alter",
    "attach",
    "pragma",
    "replace",
    "truncate",
    "create",
    "grant",
    "revoke",
)


def check_sql(sql: str) -> Tuple[bool, Optional[str]]:
    """Return (ok, reason). reason is set when ok is False."""
    text = (sql or "").strip()
    if not text:
        return False, "empty SQL"

    # Single statement only
    if ";" in text.rstrip(";"):
        return False, "multiple statements not allowed"

    body = text.rstrip(";").strip()
    lower = body.lower()

    if not lower.startswith("select"):
        return False, "only SELECT is allowed"

    for word in FORBIDDEN:
        if re.search(r"\b" + word + r"\b", lower):
            return False, "forbidden keyword: {0}".format(word)

    tables = set(re.findall(r"\bfrom\s+([a-zA-Z_][\w]*)", lower))
    tables |= set(re.findall(r"\bjoin\s+([a-zA-Z_][\w]*)", lower))
    if not tables:
        return False, "no table found"
    unknown = tables - ALLOWED_TABLES
    if unknown:
        return False, "table not allowlisted: {0}".format(
            ", ".join(sorted(unknown))
        )

    if not re.search(r"\blimit\s+\d+", lower):
        return False, "LIMIT is required"

    return True, None
