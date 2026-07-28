"""Rule-first hybrid router. Ambiguous/clarify -> both."""

from __future__ import annotations

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


def route_query(query: str) -> str:
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
