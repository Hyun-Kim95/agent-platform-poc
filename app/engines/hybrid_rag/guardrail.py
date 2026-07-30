"""T2SQL Guardrail: sqlparse (comments) + sqlglot AST policy."""

from __future__ import annotations

from typing import Optional, Set, Tuple

import sqlglot
import sqlparse
from sqlglot import exp
from sqlglot.errors import ParseError
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
# PoC analytics whitelist (sqlglot sql_name()).
_ALLOWED_FUNCS = frozenset(
    {
        "SUM",
        "COUNT",
        "AVG",
        "MIN",
        "MAX",
        "COALESCE",
        "ROUND",
        "ABS",
        "LENGTH",
        "LOWER",
        "UPPER",
        "TRIM",
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


def _sqlparse_gate(text: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Return (ok, reason, cleaned_single_statement)."""
    statements = [s for s in sqlparse.parse(text) if str(s).strip()]
    if not statements:
        return False, "empty SQL", None
    if len(statements) > 1:
        return False, "multiple statements not allowed", None

    stmt = statements[0]
    if stmt.get_type() != "SELECT":
        return False, "only SELECT is allowed", None

    for token in stmt.flatten():
        if token.ttype in Comment:
            continue
        if token.ttype in Keyword or (
            token.ttype is not None and token.ttype.parent is Keyword
        ):
            word = token.value.upper()
            if word in _FORBIDDEN:
                return False, "forbidden keyword: {0}".format(word.lower()), None

    cleaned = _without_comments(str(stmt)).rstrip(";").strip()
    if not cleaned:
        return False, "empty SQL", None
    return True, None, cleaned


def _check_ast(cleaned: str) -> Tuple[bool, Optional[str]]:
    try:
        tree = sqlglot.parse_one(cleaned, read="sqlite")
    except ParseError as exc:
        return False, "parse error: {0}".format(str(exc).splitlines()[0][:160])

    if isinstance(tree, exp.Union) or tree.find(exp.Union):
        return False, "UNION not allowed"

    if not isinstance(tree, exp.Select):
        return False, "only SELECT is allowed"

    # Nested SELECT / subquery (derived table, scalar subquery, EXISTS, …)
    selects = list(tree.find_all(exp.Select))
    if len(selects) > 1 or tree.find(exp.Subquery) or tree.find(exp.Exists):
        return False, "subquery not allowed"

    if tree.find(exp.Into):
        return False, "INTO not allowed"

    tables: Set[str] = set()
    for t in tree.find_all(exp.Table):
        name = (t.name or "").lower()
        if name:
            tables.add(name)
    if not tables:
        return False, "no table found"
    unknown = tables - ALLOWED_TABLES
    if unknown:
        return False, "table not allowlisted: {0}".format(
            ", ".join(sorted(unknown))
        )

    if tree.args.get("limit") is None:
        return False, "LIMIT is required"

    for fn in tree.find_all(exp.Func):
        if isinstance(fn, (exp.Cast, exp.TryCast, exp.Extract)):
            continue
        try:
            name = fn.sql_name().upper()
        except Exception:  # noqa: BLE001
            name = type(fn).__name__.upper()
        if name == "ANONYMOUS":
            raw = ""
            if hasattr(fn, "this") and fn.this is not None:
                raw = str(fn.this).upper()
            elif hasattr(fn, "name") and fn.name:
                raw = str(fn.name).upper()
            check = raw or name
            if check not in _ALLOWED_FUNCS:
                return False, "function not allowlisted: {0}".format(check)
            continue
        if name not in _ALLOWED_FUNCS:
            return False, "function not allowlisted: {0}".format(name)

    return True, None


def check_sql(sql: str) -> Tuple[bool, Optional[str]]:
    """Return (ok, reason). reason is set when ok is False."""
    text = (sql or "").strip()
    if not text:
        return False, "empty SQL"

    ok, reason, cleaned = _sqlparse_gate(text)
    if not ok or cleaned is None:
        return False, reason

    return _check_ast(cleaned)
