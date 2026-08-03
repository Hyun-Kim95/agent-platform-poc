"""Unit smoke for tool_router (no HTTP server)."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.models import EngineContext
from app.engines.tool_router import ToolRouterEngine


def _ctx(query: str) -> EngineContext:
    return EngineContext(
        tenant_id="internal",
        query=query,
        thread_id=None,
        trace_id=str(uuid.uuid4()),
        run_id="run_smoke_tr_{0}".format(uuid.uuid4().hex[:8]),
        timeout_ms=120_000,
        hitl_enabled=False,
        rules_only=True,
    )


def main() -> int:
    eng = ToolRouterEngine()

    calc = eng.run(_ctx("12 + 5 계산해줘"))
    assert calc.meta.engine == "tool_router"
    assert calc.status.value == "completed"
    assert calc.meta.route == "calc"
    assert any(c.type == "tool" and c.ref == "calc" for c in calc.citations)
    assert "17" in (calc.answer or "")
    print("OK calc", calc.answer)

    clock = eng.run(_ctx("지금 시각 알려줘"))
    assert clock.meta.route == "clock"
    assert any(c.ref == "clock" for c in clock.citations)
    print("OK clock", clock.answer)

    faq = eng.run(_ctx("환불 정책이 어떻게 되나요?"))
    assert faq.meta.route == "faq"
    assert "환불" in (faq.answer or "")
    print("OK faq", faq.answer)

    miss = eng.run(_ctx("하늘은 왜 파란가요?"))
    assert miss.meta.route == "none"
    assert any(c.type == "no_hit" for c in miss.citations)
    print("OK none", miss.answer)

    both = eng.run(_ctx("3*4 계산하고 지금 시간도"))
    assert both.meta.route == "both"
    refs = {c.ref for c in both.citations if c.type == "tool"}
    assert "calc" in refs and "clock" in refs
    print("OK both", both.answer)

    fetch = eng.run(_ctx("https://example.com 페이지 가져와"))
    assert fetch.meta.route == "fetch"
    assert any(c.type == "tool" and c.ref == "fetch" for c in fetch.citations)
    assert "example.com" in (fetch.answer or "").lower()
    print("OK fetch", (fetch.answer or "")[:120])

    blocked = eng.run(_ctx("http://127.0.0.1/ 가져와"))
    assert blocked.meta.route == "fetch"
    assert any(
        c.type == "no_hit" and c.ref == "fetch" for c in blocked.citations
    ) or "blocked" in (blocked.answer or "").lower()
    print("OK fetch ssrf", blocked.answer)

    print("smoke_tool_router: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
