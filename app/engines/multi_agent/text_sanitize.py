"""Sanitize web snippets for HITL draft / UI (PoC heuristics)."""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import List, Pattern, Tuple
from urllib.parse import urlparse

from app.core.config import ROOT

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Opening ```lang optional newline, body, closing ```
_FENCE_BLOCK = re.compile(r"```([\w+-]*)\n?(.*?)```", re.DOTALL)
_FENCE_TICKS = re.compile(r"```+")

_BOILER_PATH = ROOT / "configs" / "snippet_boilerplate.txt"


@lru_cache(maxsize=1)
def _boiler_patterns() -> Tuple[Tuple[Pattern[str], ...], Tuple[Pattern[str], ...]]:
    """Load deny patterns from configs/snippet_boilerplate.txt."""
    line_pats: List[Pattern[str]] = []
    inline_pats: List[Pattern[str]] = []
    if not _BOILER_PATH.is_file():
        return tuple(line_pats), tuple(inline_pats)
    for raw in _BOILER_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("line:"):
            body = line[5:].strip()
            if body:
                line_pats.append(re.compile(body, re.IGNORECASE))
            continue
        if line.startswith("inline:"):
            body = line[7:].strip()
        else:
            body = line
        if body:
            inline_pats.append(re.compile(body, re.IGNORECASE))
    return tuple(line_pats), tuple(inline_pats)


def reload_boiler_patterns() -> None:
    """Clear cache after editing the config (tests / REPL)."""
    _boiler_patterns.cache_clear()


def _mojibake_score(text: str) -> float:
    if not text:
        return 0.0
    weird = 0
    for ch in text:
        if ch == "\ufffd":
            weird += 3
            continue
        o = ord(ch)
        cat = unicodedata.category(ch)
        if cat == "Mn" or 0x02B0 <= o <= 0x02FF:
            weird += 2
        elif cat == "Cn":
            weird += 2
        elif 0x0180 <= o <= 0x024F:
            weird += 1
        elif 0x00A0 <= o <= 0x00FF:
            weird += 1
    return weird / float(max(len(text), 1))


def _unwrap_fence_match(match: re.Match) -> str:
    """Keep fence inner text; drop ``` markers."""
    inner = (match.group(2) or "").strip()
    if not inner:
        return " "
    return " " + inner + " "


def _strip_fences(text: str) -> str:
    s = _FENCE_BLOCK.sub(_unwrap_fence_match, text)
    s = _FENCE_TICKS.sub(" ", s)
    return s


def _strip_boilerplate(text: str) -> str:
    line_pats, inline_pats = _boiler_patterns()
    kept = []
    for line in text.splitlines():
        if any(p.search(line) for p in line_pats):
            continue
        cleaned = line
        for pat in inline_pats:
            cleaned = pat.sub(" ", cleaned)
        cleaned = cleaned.strip()
        if cleaned:
            kept.append(cleaned)
    return "\n".join(kept)


def short_url_host(url: str, max_len: int = 48) -> str:
    """Host-only display for answer lines (R3)."""
    if not url:
        return ""
    try:
        host = urlparse(str(url)).netloc or ""
    except Exception:
        host = ""
    if host:
        if len(host) > max_len:
            return host[: max_len - 1] + "…"
        return host
    return sanitize_snippet(str(url), max_len=max_len)


def sanitize_snippet(text: str, max_len: int = 120) -> str:
    """Unwrap fences, strip boilerplate/controls, truncate, or flag mojibake."""
    if not text:
        return ""
    s = _CTRL.sub("", str(text))
    s = _strip_fences(s)
    s = _strip_boilerplate(s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = s.strip()
    if not s:
        return "(snippet cleaned)"
    if _mojibake_score(s) >= 0.12:
        return "(encoding unclear)"
    if len(s) > max_len:
        return s[: max_len - 1].rstrip() + "…"
    return s
