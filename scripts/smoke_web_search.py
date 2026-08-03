"""Unit smoke: web search source is mock or tavily (visible, not silent)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.engines.multi_agent.tools_search import search_web


def main() -> int:
    cfg = get_settings()
    key = (cfg.web_search_api_key or "").strip()
    hits, source, reason = search_web("AI agents overview", max_results=2)
    print("key_set=", bool(key), "source=", source, "reason=", reason)
    assert hits, "expected hits"
    assert source in ("tavily", "mock"), source
    if not key:
        assert source == "mock" and reason == "no_key"
        assert all("example.com" in (h.get("url") or "") for h in hits)
        print("OK mock path (no WEB_SEARCH_API_KEY)")
    else:
        if source == "tavily":
            assert not all(
                "example.com" in (h.get("url") or "") for h in hits
            ), hits
            print("OK tavily path", hits[0].get("url"))
        else:
            assert reason in (
                "http_error",
                "empty_results",
                "unsupported_provider",
            ), reason
            print("OK keyed but fell back to mock reason=", reason)
    print("smoke_web_search: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
