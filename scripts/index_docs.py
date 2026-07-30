"""Reindex samples/docs into pgvector."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.engines.hybrid_rag.vector_store import index_docs


def main() -> None:
    n, usage = index_docs(force=True)
    print("indexed={0} usage={1}".format(n, usage))


if __name__ == "__main__":
    main()
