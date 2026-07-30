"""Build answer text from tool results."""

from __future__ import annotations

from typing import Any, Dict, List


def synthesize(
    query: str,
    results: List[Dict[str, Any]],
    *,
    route_source: str,
) -> str:
    if not results:
        return (
            "맞는 툴을 고르지 못했습니다. "
            "계산식, 현재 시각, 환불/비밀번호/영업시간 FAQ를 물어보세요."
            " (route={0})".format(route_source)
        )

    lines = []
    for r in results:
        name = r.get("name") or "?"
        if r.get("ok"):
            lines.append("[{0}] {1}".format(name, r.get("text") or ""))
        else:
            lines.append(
                "[{0}] failed: {1}".format(name, r.get("text") or "error")
            )
    return "\n".join(lines)
