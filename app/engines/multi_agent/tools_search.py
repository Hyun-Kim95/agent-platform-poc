"""Web search tool: Tavily if keyed, else mock fixtures."""

from __future__ import annotations

from typing import Any, Dict, List

import httpx

from app.core.config import get_settings


def search_web(query: str, max_results: int = 3) -> List[Dict[str, Any]]:
    settings = get_settings()
    key = (settings.web_search_api_key or "").strip()
    if not key:
        return _mock_hits(query, max_results)

    provider = (settings.web_search_provider or "tavily").lower()
    if provider != "tavily":
        return _mock_hits(query, max_results)

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
    except Exception:
        return _mock_hits(query, max_results)

    hits: List[Dict[str, Any]] = []
    for item in data.get("results") or []:
        hits.append(
            {
                "url": item.get("url") or "",
                "title": item.get("title") or "",
                "snippet": item.get("content") or item.get("snippet") or "",
            }
        )
        if len(hits) >= max_results:
            break
    return hits or _mock_hits(query, max_results)


def _mock_hits(query: str, max_results: int) -> List[Dict[str, Any]]:
    samples = [
        {
            "url": "https://example.com/ai-agents-overview",
            "title": "AI agents overview (mock)",
            "snippet": "Mock article summarizing public AI agent trends for query: {0}".format(
                query[:80]
            ),
        },
        {
            "url": "https://example.com/multi-agent-systems",
            "title": "Multi-agent systems notes (mock)",
            "snippet": "Mock notes on routing, tools, and human review loops.",
        },
    ]
    return samples[:max_results]
