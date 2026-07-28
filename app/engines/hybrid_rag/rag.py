"""Keyword + chunk retrieval over samples/docs/*.md."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[3]
DOCS_DIR = ROOT / "samples" / "docs"


def _tokenize(text: str) -> List[str]:
    return [t for t in re.split(r"[^\w가-힣]+", text.lower()) if t]


def _chunk_markdown(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"\n(?=#{1,3}\s)", text)
    chunks: List[Dict[str, Any]] = []
    idx = 0
    for part in parts:
        body = part.strip()
        if not body:
            continue
        title = body.splitlines()[0].lstrip("#").strip() or path.stem
        chunks.append(
            {
                "path": path,
                "index": idx,
                "title": title,
                "text": body,
            }
        )
        idx += 1
    if not chunks:
        chunks.append(
            {
                "path": path,
                "index": 0,
                "title": path.stem,
                "text": text.strip() or path.name,
            }
        )
    return chunks


def retrieve(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    if not DOCS_DIR.is_dir():
        return []

    q_tokens = set(_tokenize(query))
    scored: List[Dict[str, Any]] = []
    for path in sorted(DOCS_DIR.glob("*.md")):
        for ch in _chunk_markdown(path):
            c_tokens = set(_tokenize(ch["text"]))
            overlap = q_tokens & c_tokens
            if not overlap:
                continue
            rel = path.relative_to(ROOT).as_posix()
            scored.append(
                {
                    "score": len(overlap),
                    "citation": {
                        "type": "doc",
                        "ref": "{0}#chunk-{1}".format(rel, ch["index"]),
                        "title": ch["title"],
                        "snippet": ch["text"][:240],
                    },
                    "text": ch["text"],
                }
            )

    scored.sort(key=lambda x: (-x["score"], x["citation"]["ref"]))
    return scored[:top_k]
