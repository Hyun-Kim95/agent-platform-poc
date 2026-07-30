"""Rule-first tool router; optional LLM when ambiguous."""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from app.core.config import Settings, get_settings
from app.core.models import TokenUsage
from app.engines.tool_router.tools import extract_math_expr
from app.llm.client import LlmError, chat_completion

CALC_KEYS = ("계산", "calc", "calculate", "더하기", "곱하기")
CLOCK_KEYS = (
    "지금",
    "시각",
    "시간",
    "날짜",
    "몇 시",
    "now",
    "time",
    "date",
    "utc",
    "clock",
)
FAQ_KEYS = (
    "환불",
    "refund",
    "반품",
    "비밀번호",
    "password",
    "비번",
    "로그인",
    "영업시간",
    "고객센터",
    "문의",
    "support",
)

_SYSTEM = (
    "You pick tools for a PoC agent. "
    "Reply with a comma-separated subset of: calc, clock, faq "
    "or exactly: none. Max two tools. No explanation."
)


def _has_any(query: str, keys: tuple) -> bool:
    q = query or ""
    ql = q.lower()
    return any(k.lower() in ql or k in q for k in keys)


def detect_tools_rules(query: str) -> List[str]:
    found: List[str] = []
    if extract_math_expr(query) or _has_any(query, CALC_KEYS):
        found.append("calc")
    if _has_any(query, CLOCK_KEYS):
        found.append("clock")
    if _has_any(query, FAQ_KEYS):
        found.append("faq")
    return found[:2]


def _is_ambiguous(query: str, rules: List[str]) -> bool:
    if not rules:
        return True
    if len(rules) >= 2:
        return True
    return False


def _parse_tools(text: str) -> Optional[List[str]]:
    t = (text or "").strip().lower()
    if t == "none" or t == "clarify":
        return []
    parts = re.split(r"[\s,|/]+", t)
    out: List[str] = []
    for p in parts:
        p = p.strip()
        if p in ("calc", "clock", "faq") and p not in out:
            out.append(p)
        if len(out) >= 2:
            break
    if out:
        return out
    return None


def route_tools(
    query: str,
    *,
    rules_only: bool = False,
    settings: Optional[Settings] = None,
) -> Tuple[List[str], Optional[TokenUsage], str]:
    """Return (tool_names, usage, source). source: rules|llm|rules_fallback."""
    cfg = settings or get_settings()
    rules = detect_tools_rules(query)

    use_llm = (
        not rules_only
        and bool((cfg.llm_api_key or "").strip())
        and _is_ambiguous(query, rules)
    )
    if not use_llm:
        return rules, None, "rules"

    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": "Question: {0}".format(query or "")},
    ]
    try:
        text, usage = chat_completion(messages, settings=cfg, temperature=0.0)
    except LlmError:
        return rules, None, "rules_fallback"

    parsed = _parse_tools(text)
    if parsed is None:
        return rules, None, "rules_fallback"
    return parsed, usage, "llm"
