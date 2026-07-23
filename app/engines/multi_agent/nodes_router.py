"""Router node: rule-first keywords. Ambiguous/clarify -> both."""

from __future__ import annotations

from app.engines.multi_agent.state import AgentState

WEB_KEYS = (
    "기사",
    "뉴스",
    "최근",
    "검색",
    "웹",
    "공개",
    "article",
    "news",
    "web",
)
DATA_KEYS = (
    "csv",
    "매출",
    "합계",
    "집계",
    "표",
    "mini.csv",
    "데이터",
    "revenue",
    "합",
)


def node_router(state: AgentState) -> AgentState:
    query = state.get("query") or ""
    q_lower = query.lower()
    has_web = any(k.lower() in q_lower or k in query for k in WEB_KEYS)
    has_data = any(k.lower() in q_lower or k in query for k in DATA_KEYS)

    if has_web and has_data:
        route = "both"
    elif has_web:
        route = "web"
    elif has_data:
        route = "data"
    else:
        route = "both"

    state["route"] = route
    state["citations"] = list(state.get("citations") or [])
    state["risks"] = list(state.get("risks") or [])
    state["ok"] = True
    return state
