"""Shared Citation conversion for engines."""

from __future__ import annotations

from typing import Any, Dict, List

from app.core.models import Citation

ALLOWED_CITATION_TYPES = frozenset({"web", "data", "doc", "sql", "no_hit"})


def to_citation(raw: Dict[str, Any]) -> Citation:
    ctype = raw.get("type") or "no_hit"
    if ctype not in ALLOWED_CITATION_TYPES:
        ctype = "no_hit"
    return Citation(
        type=ctype,  # type: ignore[arg-type]
        ref=raw.get("ref") or "",
        title=raw.get("title") or "",
        snippet=raw.get("snippet"),
    )


def citations_or_fallback(raw: List[Dict[str, Any]]) -> List[Citation]:
    out = [to_citation(c) for c in raw]
    if not out:
        out.append(
            Citation(
                type="no_hit",
                ref="",
                title="no citations produced",
                snippet=None,
            )
        )
    return out
