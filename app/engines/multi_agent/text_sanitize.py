"""Sanitize web snippets for HITL draft / UI (PoC heuristics)."""

from __future__ import annotations

import re
import unicodedata

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


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
        # Combining marks / modifiers often show up in CP949 mis-decodes (e.g. U+033E).
        if cat == "Mn" or 0x02B0 <= o <= 0x02FF:
            weird += 2
        elif cat == "Cn":
            weird += 2
        elif 0x0180 <= o <= 0x024F:
            # Latin Extended-B junk frequent in broken KR pages
            weird += 1
        elif 0x00A0 <= o <= 0x00FF:
            weird += 1
    return weird / float(max(len(text), 1))


def sanitize_snippet(text: str, max_len: int = 120) -> str:
    """Strip controls, truncate, or replace high-mojibake text."""
    if not text:
        return ""
    s = _CTRL.sub("", str(text))
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = s.strip()
    if not s:
        return ""
    if _mojibake_score(s) >= 0.12:
        return "(encoding unclear)"
    if len(s) > max_len:
        return s[: max_len - 1].rstrip() + "…"
    return s
