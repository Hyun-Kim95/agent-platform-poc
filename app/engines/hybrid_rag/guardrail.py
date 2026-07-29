"""T2SQL Guardrail: sqlparse + allowlist + LIMIT (comment-safe)."""

from __future__ import annotations

import re
from typing import Optional, Tuple

import sqlparse
from sqlparse.tokens import Comment, Keyword

ALLOWED_TABLES = frozenset({"sales"})
_FORBIDDEN = frozenset(
    {
        "DROP",
        "DELETE",
        "UPDATE",
        "INSERT",
        "ALTER",
        "ATTACH",
        "PRAGMA",
        "REPLACE",
        "TRUNCATE",
        "CREATE",
        "GRANT",
        "REVOKE",
    }
)


def _without_comments(sql: str) -> str:
    """Rebuild SQL text with comment tokens removed."""
    parts = []
    for stmt in sqlparse.parse(sql):
        for token in stmt.flatten():
            if token.ttype in Comment:
                continue
            parts.append(token.value)
    return "".join(parts).strip()


def check_sql(sql: str) -> Tuple[bool, Optional[str]]:
    """Return (ok, reason). reason is set when ok is False."""
    text = (sql or "").strip()
    if not text:
        return False, "empty SQL"

    statements = [s for s in sqlparse.parse(text) if str(s).strip()]
    if not statements:
        return False, "empty SQL"
    if len(statements) > 1:
        return False, "multiple statements not allowed"

    stmt = statements[0]
    if stmt.get_type() != "SELECT":
        return False, "only SELECT is allowed"

    for token in stmt.flatten():
        if token.ttype in Comment:
            continue
        # Keyword / DML-like tokens (sqlparse marks DROP etc. as Keyword)
        if token.ttype in Keyword or (
            token.ttype is not None and token.ttype.parent is Keyword
        ):
            word = token.value.upper()
            if word in _FORBIDDEN:
                return False, "forbidden keyword: {0}".format(word.lower())

    cleaned = _without_comments(str(stmt)).rstrip(";").strip()
    lower = cleaned.lower()
    if not lower:
        return False, "empty SQL"

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
