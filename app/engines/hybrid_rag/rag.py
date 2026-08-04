"""Keyword + optional pgvector retrieval over samples/docs (multi-collection)."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import Settings, get_settings
from app.core.models import TokenUsage

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
DOCS_DIR = ROOT / "samples" / "docs"


def _tokenize(text: str) -> List[str]:
    return [t for t in re.split(r"[^\w가-힣]+", text.lower()) if t]


def _is_title_only(body: str) -> bool:
    """True when chunk is only a markdown heading line (no body)."""
    lines = [ln for ln in body.splitlines() if ln.strip()]
    if len(lines) != 1:
        return False
    return bool(re.match(r"#{1,3}\s+\S", lines[0]))


def iter_doc_files() -> List[Tuple[Path, str]]:
    """Return (absolute path, collection name).

    - samples/docs/foo.md -> collection ``default``
    - samples/docs/policy/foo.md -> collection ``policy``
    """
    if not DOCS_DIR.is_dir():
        return []
    out: List[Tuple[Path, str]] = []
    for path in sorted(DOCS_DIR.rglob("*.md")):
        rel_parent = path.parent.relative_to(DOCS_DIR)
        if rel_parent == Path("."):
            collection = "default"
        else:
            collection = rel_parent.parts[0]
        out.append((path, collection))
    return out


def _split_char_windows(text: str, size: int, overlap: int) -> List[str]:
    if size <= 0 or len(text) <= size:
        return [text]
    overlap = max(0, min(overlap, size - 1))
    step = max(1, size - overlap)
    windows: List[str] = []
    i = 0
    while i < len(text):
        windows.append(text[i : i + size])
        if i + size >= len(text):
            break
        i += step
    return windows


def chunk_document(
    path: Path,
    *,
    chunk_size: int = 0,
    chunk_overlap: int = 64,
) -> List[Dict[str, Any]]:
    """Heading split, then optional character windows when chunk_size > 0."""
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"\n(?=#{1,3}\s)", text)
    sections: List[Tuple[str, str]] = []
    for part in parts:
        body = part.strip()
        if not body:
            continue
        if _is_title_only(body):
            continue
        title = body.splitlines()[0].lstrip("#").strip() or path.stem
        sections.append((title, body))
    if not sections:
        sections.append((path.stem, text.strip() or path.name))

    chunks: List[Dict[str, Any]] = []
    idx = 0
    for title, body in sections:
        pieces = (
            _split_char_windows(body, chunk_size, chunk_overlap)
            if chunk_size > 0
            else [body]
        )
        for piece in pieces:
            piece = piece.strip()
            if not piece:
                continue
            chunks.append(
                {
                    "path": path,
                    "index": idx,
                    "title": title,
                    "text": piece,
                }
            )
            idx += 1
    return chunks


def _chunk_markdown(path: Path) -> List[Dict[str, Any]]:
    """Backward-compatible wrapper (heading-only)."""
    return chunk_document(path, chunk_size=0, chunk_overlap=0)


def chunk_strategy_name(chunk_size: int) -> str:
    return "heading_char" if chunk_size > 0 else "heading"


def rerank_token_overlap(
    query: str,
    passages: List[Dict[str, Any]],
    top_k: int,
) -> List[Dict[str, Any]]:
    q_tokens = set(_tokenize(query))
    scored: List[Tuple[int, Dict[str, Any]]] = []
    for p in passages:
        text = p.get("text") or ""
        ov = len(q_tokens & set(_tokenize(text)))
        scored.append((ov, p))
    scored.sort(
        key=lambda item: (
            -item[0],
            (item[1].get("citation") or {}).get("ref") or "",
        )
    )
    out: List[Dict[str, Any]] = []
    for ov, p in scored[:top_k]:
        row = dict(p)
        row["score"] = float(ov)
        out.append(row)
    return out


def retrieve_keyword(
    query: str,
    top_k: int = 3,
    *,
    collection: Optional[str] = None,
    chunk_size: int = 0,
    chunk_overlap: int = 64,
) -> List[Dict[str, Any]]:
    if not DOCS_DIR.is_dir():
        return []

    q_tokens = set(_tokenize(query))
    scored: List[Dict[str, Any]] = []
    for path, coll in iter_doc_files():
        if collection and coll != collection:
            continue
        for ch in chunk_document(
            path, chunk_size=chunk_size, chunk_overlap=chunk_overlap
        ):
            c_tokens = set(_tokenize(ch["text"]))
            overlap = q_tokens & c_tokens
            if not overlap:
                continue
            rel = path.relative_to(ROOT).as_posix()
            scored.append(
                {
                    "score": len(overlap),
                    "collection": coll,
                    "citation": {
                        "type": "doc",
                        "ref": "{0}:{1}#chunk-{2}".format(
                            coll, rel, ch["index"]
                        ),
                        "title": ch["title"],
                        "snippet": ch["text"][:240],
                    },
                    "text": ch["text"],
                }
            )

    scored.sort(key=lambda x: (-x["score"], x["citation"]["ref"]))
    return scored[:top_k]


def retrieve(
    query: str,
    top_k: Optional[int] = None,
    *,
    settings: Optional[Settings] = None,
    collection: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], str, Optional[TokenUsage], Dict[str, Any]]:
    """Return (passages, rag_source, embed_usage, rag_meta)."""
    cfg = settings or get_settings()
    top_k = int(top_k if top_k is not None else cfg.rag_top_k)
    candidate_k = max(top_k, int(cfg.rag_candidate_k))
    coll = (
        collection if collection is not None else cfg.rag_collection or ""
    ).strip() or None
    chunk_size = int(cfg.rag_chunk_size)
    chunk_overlap = int(cfg.rag_chunk_overlap)
    strategy = chunk_strategy_name(chunk_size)
    do_rerank = bool(cfg.rag_rerank)

    rag_meta: Dict[str, Any] = {
        "rag_collection": coll,
        "chunk_strategy": strategy,
        "rag_rerank": "none",
    }

    from app.engines.hybrid_rag import vector_store

    if vector_store.available(cfg):
        try:
            vector_store.index_docs(settings=cfg, force=False)
            passages, usage = vector_store.search(
                query,
                top_k=candidate_k if do_rerank else top_k,
                settings=cfg,
                collection=coll,
            )
            if passages:
                if do_rerank and len(passages) > 1:
                    passages = rerank_token_overlap(query, passages, top_k)
                    rag_meta["rag_rerank"] = "token_overlap"
                else:
                    passages = passages[:top_k]
                return passages, "vector", usage, rag_meta
        except Exception as exc:  # noqa: BLE001
            logger.warning("vector retrieve failed, keyword fallback: %s", exc)

    passages = retrieve_keyword(
        query,
        top_k=top_k,
        collection=coll,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    if do_rerank and passages:
        passages = rerank_token_overlap(query, passages, top_k)
        rag_meta["rag_rerank"] = "token_overlap"
    source = "keyword" if passages else "none"
    return passages, source, None, rag_meta
