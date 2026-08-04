"""pgvector store for hybrid_rag document chunks (vectors only)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import Settings, get_settings
from app.core.models import TokenUsage
from app.engines.hybrid_rag.rag import (
    ROOT,
    chunk_document,
    iter_doc_files,
)
from app.llm.client import LlmError
from app.llm.embeddings import embed_texts
from app.llm.usage import merge_usage

logger = logging.getLogger(__name__)

EMBED_DIM = 1536


def _connect(url: str):
    import psycopg
    from pgvector.psycopg import register_vector

    conn = psycopg.connect(url)
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.commit()
    register_vector(conn)
    return conn


def available(settings: Optional[Settings] = None) -> bool:
    cfg = settings or get_settings()
    url = (cfg.vector_database_url or "").strip()
    if not url:
        return False
    if not (cfg.llm_api_key or "").strip():
        return False
    try:
        with _connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("pgvector unavailable: %s", exc)
        return False


def ensure_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS doc_chunks (
                id TEXT PRIMARY KEY,
                collection TEXT NOT NULL DEFAULT 'default',
                path TEXT NOT NULL,
                chunk_index INT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL,
                content_sha TEXT NOT NULL,
                embedding vector({0}) NOT NULL
            )
            """.format(
                EMBED_DIM
            )
        )
        # Brownfield: add column if table existed without collection.
        cur.execute(
            """
            ALTER TABLE doc_chunks
            ADD COLUMN IF NOT EXISTS collection TEXT NOT NULL DEFAULT 'default'
            """
        )
        cur.execute("DROP INDEX IF EXISTS doc_chunks_path_idx")
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS doc_chunks_coll_path_idx
            ON doc_chunks (collection, path, chunk_index)
            """
        )
    conn.commit()


def _chunk_id(collection: str, rel: str, index: int) -> str:
    return "{0}:{1}#{2}".format(collection, rel, index)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def index_docs(
    *,
    settings: Optional[Settings] = None,
    force: bool = False,
    only_collection: Optional[str] = None,
) -> Tuple[int, Optional[TokenUsage]]:
    """Upsert sample docs. Returns (upserted_count, embed_usage)."""
    cfg = settings or get_settings()
    url = (cfg.vector_database_url or "").strip()
    if not url:
        raise LlmError("VECTOR_DATABASE_URL is empty")

    chunk_size = int(cfg.rag_chunk_size)
    chunk_overlap = int(cfg.rag_chunk_overlap)
    rows: List[Dict[str, Any]] = []
    for path, collection in iter_doc_files():
        if only_collection and collection != only_collection:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for ch in chunk_document(
            path, chunk_size=chunk_size, chunk_overlap=chunk_overlap
        ):
            body = ch["text"]
            rows.append(
                {
                    "id": _chunk_id(collection, rel, ch["index"]),
                    "collection": collection,
                    "path": rel,
                    "chunk_index": ch["index"],
                    "title": ch["title"],
                    "body": body,
                    "content_sha": _sha(body),
                }
            )

    usage_acc: Optional[TokenUsage] = None
    with _connect(url) as conn:
        ensure_schema(conn)
        to_embed: List[Dict[str, Any]] = []
        with conn.cursor() as cur:
            for row in rows:
                if force:
                    to_embed.append(row)
                    continue
                cur.execute(
                    "SELECT content_sha FROM doc_chunks WHERE id = %s",
                    (row["id"],),
                )
                got = cur.fetchone()
                if got is None or got[0] != row["content_sha"]:
                    to_embed.append(row)

        if not to_embed:
            return 0, None

        texts = [r["body"] for r in to_embed]
        batch = 32
        vectors: List[List[float]] = []
        for i in range(0, len(texts), batch):
            part, usage = embed_texts(texts[i : i + batch], settings=cfg)
            vectors.extend(part)
            usage_acc = merge_usage(usage_acc, usage)

        with conn.cursor() as cur:
            for row, vec in zip(to_embed, vectors):
                if len(vec) != EMBED_DIM:
                    raise LlmError(
                        "unexpected embedding dim {0}".format(len(vec))
                    )
                cur.execute(
                    """
                    INSERT INTO doc_chunks
                      (id, collection, path, chunk_index, title, body,
                       content_sha, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                      collection = EXCLUDED.collection,
                      title = EXCLUDED.title,
                      body = EXCLUDED.body,
                      content_sha = EXCLUDED.content_sha,
                      embedding = EXCLUDED.embedding
                    """,
                    (
                        row["id"],
                        row["collection"],
                        row["path"],
                        row["chunk_index"],
                        row["title"],
                        row["body"],
                        row["content_sha"],
                        vec,
                    ),
                )
        conn.commit()
    return len(to_embed), usage_acc


def search(
    query: str,
    *,
    top_k: int = 3,
    settings: Optional[Settings] = None,
    collection: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Optional[TokenUsage]]:
    """Return (passage dicts like keyword retrieve, query embed usage)."""
    cfg = settings or get_settings()
    url = (cfg.vector_database_url or "").strip()
    q_vecs, usage = embed_texts([query or ""], settings=cfg)
    q = q_vecs[0]

    out: List[Dict[str, Any]] = []
    with _connect(url) as conn:
        ensure_schema(conn)
        with conn.cursor() as cur:
            if collection:
                cur.execute(
                    """
                    SELECT collection, path, chunk_index, title, body,
                           embedding <=> %s::vector AS dist
                    FROM doc_chunks
                    WHERE collection = %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (q, collection, q, top_k),
                )
            else:
                cur.execute(
                    """
                    SELECT collection, path, chunk_index, title, body,
                           embedding <=> %s::vector AS dist
                    FROM doc_chunks
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (q, q, top_k),
                )
            for coll, path, idx, title, body, _dist in cur.fetchall():
                out.append(
                    {
                        "score": 0.0,
                        "collection": coll,
                        "citation": {
                            "type": "doc",
                            "ref": "{0}:{1}#chunk-{2}".format(
                                coll, path, idx
                            ),
                            "title": title,
                            "snippet": (body or "")[:240],
                        },
                        "text": body,
                    }
                )
    return out, usage
