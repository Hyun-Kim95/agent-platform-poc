"""Build a plain-text answer from RAG passages and SQL rows."""

from __future__ import annotations

from typing import Any, Dict, List


def synthesize(
    query: str,
    route: str,
    passages: List[Dict[str, Any]],
    sql: str,
    columns: List[str],
    rows: List[Dict[str, Any]],
) -> str:
    parts = [
        "## Hybrid answer",
        "",
        "Query: {0}".format(query),
        "Route: {0}".format(route),
    ]

    if route in ("rag", "both"):
        parts.append("")
        parts.append("### Documents")
        if passages:
            for p in passages:
                cite = p.get("citation") or {}
                parts.append(
                    "- {0} ({1})".format(
                        cite.get("title") or "",
                        cite.get("ref") or "",
                    )
                )
                parts.append("  {0}".format((p.get("text") or "")[:200]))
        else:
            parts.append("- (no document hits)")

    if route in ("sql", "both") and sql:
        parts.append("")
        parts.append("### SQL")
        parts.append("```sql")
        parts.append(sql)
        parts.append("```")
        if rows:
            parts.append("Rows ({0}):".format(len(rows)))
            for row in rows[:10]:
                parts.append("- {0}".format(row))
        elif columns:
            parts.append("Rows: (empty)")

    return "\n".join(parts)
