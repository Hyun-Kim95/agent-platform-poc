"""Web search tool: Tavily if keyed, else mock fixtures."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.config import get_settings


def search_web(
    query: str, max_results: int = 3
) -> Tuple[List[Dict[str, Any]], str, Optional[str]]:
    """Return (hits, source, mock_reason).

    source is ``tavily`` or ``mock``. mock_reason is set only for mock
    (no_key | unsupported_provider | http_error | empty_results).
    """
    settings = get_settings()
    key = (settings.web_search_api_key or "").strip()
    if not key:
        return _mock_hits(query, max_results), "mock", "no_key"

    provider = (settings.web_search_provider or "tavily").lower()
    if provider != "tavily":
        return (
            _mock_hits(query, max_results),
            "mock",
            "unsupported_provider",
        )

    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        hits = _mock_hits(query, max_results)
        for h in hits:
            h["mock_reason"] = "http_error"
            h["error"] = str(exc)[:200]
        return hits, "mock", "http_error"

    hits: List[Dict[str, Any]] = []
    for item in data.get("results") or []:
        hits.append(
            {
                "url": item.get("url") or "",
                "title": item.get("title") or "",
                "snippet": item.get("content") or item.get("snippet") or "",
                "source": "tavily",
            }
        )
        if len(hits) >= max_results:
            break
    if not hits:
        return _mock_hits(query, max_results), "mock", "empty_results"
    return hits, "tavily", None


def _mock_hits(query: str, max_results: int) -> List[Dict[str, Any]]:
    samples = [
        {
            "url": "https://example.com/ai-agents-overview",
            "title": "AI agents overview (mock)",
            "snippet": "Mock article summarizing public AI agent trends for query: {0}".format(
                query[:80]
            ),
            "source": "mock",
        },
        {
            "url": "https://example.com/multi-agent-systems",
            "title": "Multi-agent systems notes (mock)",
            "snippet": "Mock notes on routing, tools, and human review loops.",
            "source": "mock",
        },
    ]
    return samples[:max_results]
