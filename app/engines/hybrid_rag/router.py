"""Rule-first hybrid router; optional LLM when ambiguous."""

from __future__ import annotations

import re
from typing import Optional, Tuple

from app.core.config import Settings, get_settings
from app.core.models import TokenUsage
from app.llm.client import LlmError, chat_completion

RAG_KEYS = (
    "환불",
    "정책",
    "배송",
    "문서",
    "가이드",
    "policy",
    "refund",
    "shipping",
    "docs",
)
SQL_KEYS = (
    "매출",
    "합계",
    "revenue",
    "sql",
    "집계",
    "얼마",
    "총액",
    "sales",
    "테이블",
    "drop",
    "delete",
)

_SYSTEM = (
    "You route a user question for a hybrid RAG+SQL agent. "
    "Reply with exactly one token: rag OR sql OR both. "
    "rag = policy/docs only; sql = analytics/table only; "
    "both = needs both. No explanation."
)


def route_query_rules(query: str) -> str:
    q = query or ""
    q_lower = q.lower()
    has_rag = any(k.lower() in q_lower or k in q for k in RAG_KEYS)
    has_sql = any(k.lower() in q_lower or k in q for k in SQL_KEYS)

    if has_rag and has_sql:
        return "both"
    if has_rag:
        return "rag"
    if has_sql:
        return "sql"
    # clarify -> both (api.md)
    return "both"


def _is_ambiguous(query: str) -> bool:
    q = query or ""
    q_lower = q.lower()
    has_rag = any(k.lower() in q_lower or k in q for k in RAG_KEYS)
    has_sql = any(k.lower() in q_lower or k in q for k in SQL_KEYS)
    if has_rag and has_sql:
        return True
    if not has_rag and not has_sql:
        return True
    return False


def _parse_route_label(text: str) -> Optional[str]:
    t = (text or "").strip().lower()
    if t in ("rag", "sql", "both"):
        return t
    if t == "clarify":
        return "both"
    for cand in ("both", "rag", "sql"):
        if re.search(r"\b" + cand + r"\b", t):
            return cand
    return None


def route_query(
    query: str,
    *,
    rules_only: bool = False,
    settings: Optional[Settings] = None,
) -> Tuple[str, Optional[TokenUsage], str]:
    """
    Return (route, llm_usage_or_none, source).
    source: "rules" | "llm" | "rules_fallback"
    """
    cfg = settings or get_settings()
    rules_route = route_query_rules(query)

    use_llm = (
        not rules_only
        and bool((cfg.llm_api_key or "").strip())
        and _is_ambiguous(query)
    )
    if not use_llm:
        return rules_route, None, "rules"

    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": "Question: {0}".format(query or "")},
    ]
    try:
        text, usage = chat_completion(messages, settings=cfg, temperature=0.0)
    except LlmError:
        return rules_route, None, "rules_fallback"

    parsed = _parse_route_label(text)
    if parsed is None:
        return rules_route, None, "rules_fallback"

    return parsed, usage, "llm"
