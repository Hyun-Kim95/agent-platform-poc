"""Vector RAG smoke: skip if no VECTOR_DATABASE_URL / key / PG."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.engines.hybrid_rag import vector_store
from app.engines.hybrid_rag.rag import retrieve


def main() -> int:
    cfg = get_settings()
    if not (cfg.vector_database_url or "").strip():
        print("SKIP: VECTOR_DATABASE_URL empty")
        return 0
    if not vector_store.available(cfg):
        print("SKIP: pgvector or LLM key unavailable")
        return 0

    passages, source, _usage, meta = retrieve(
        "환불은 며칠 안에 되나요?",
        settings=cfg,
    )
    print("source=", source, "n=", len(passages), "meta=", meta)
    assert source == "vector", source
    assert passages, "expected doc hits"
    assert passages[0]["citation"]["type"] == "doc"
    print("smoke_vector_rag: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
