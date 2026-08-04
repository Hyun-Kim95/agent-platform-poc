"""Reindex samples/docs into pgvector."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.engines.hybrid_rag.vector_store import index_docs


def main(argv: Optional[List[str]] = None) -> int:
    cfg = get_settings()
    parser = argparse.ArgumentParser(description="Index docs into pgvector")
    parser.add_argument(
        "--force",
        action="store_true",
        default=True,
        help="Re-embed even when content_sha matches (default)",
    )
    parser.add_argument(
        "--no-force",
        action="store_true",
        help="Skip unchanged chunks",
    )
    parser.add_argument("--chunk-size", type=int, default=None)
    parser.add_argument("--overlap", type=int, default=None)
    parser.add_argument(
        "--collection",
        type=str,
        default=None,
        help="Index only this collection folder name",
    )
    args = parser.parse_args(argv)

    force = not args.no_force
    if args.chunk_size is not None:
        cfg.rag_chunk_size = args.chunk_size
    if args.overlap is not None:
        cfg.rag_chunk_overlap = args.overlap

    n, usage = index_docs(
        settings=cfg,
        force=force,
        only_collection=(args.collection or None),
    )
    print(
        "indexed={0} chunk_size={1} overlap={2} collection={3} usage={4}".format(
            n,
            cfg.rag_chunk_size,
            cfg.rag_chunk_overlap,
            args.collection or "(all)",
            usage,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
