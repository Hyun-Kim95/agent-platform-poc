"""Unit smoke for small fixes S1~S3 (no HTTP)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.citations import citations_or_fallback, to_citation
from app.engines.hybrid_rag.rag import _chunk_markdown, iter_doc_files
from app.engines.hybrid_rag.t2sql import generate_sql_template


def main() -> None:
    # S1: substring must NOT force DROP; whole word DROP still does
    soft = generate_sql_template("updated revenue report")
    assert not soft.upper().startswith("DROP"), soft
    print("OK  S1 soft query ->", soft[:48], "...")

    hard = generate_sql_template("sales 테이블 DROP 해줘")
    assert hard.upper().startswith("DROP"), hard
    print("OK  S1 DROP word ->", hard)

    # S2: no title-only heading chunks from sample docs
    for path, _coll in iter_doc_files():
        for ch in _chunk_markdown(path):
            lines = [ln for ln in ch["text"].splitlines() if ln.strip()]
            only_heading = (
                len(lines) == 1 and lines[0].lstrip().startswith("#")
            )
            assert not only_heading, (path.name, ch["index"], ch["text"])
        print("OK  S2 chunks", path.name)

    # S3: doc/sql survive conversion (multi_agent used to collapse them)
    doc = to_citation({"type": "doc", "ref": "a.md#0", "title": "t"})
    sql = to_citation({"type": "sql", "ref": "SELECT 1", "title": "q"})
    assert doc.type == "doc", doc
    assert sql.type == "sql", sql
    empty = citations_or_fallback([])
    assert empty[0].type == "no_hit", empty
    print("OK  S3 citation types")

    print("smoke_small_fixes: all passed")


if __name__ == "__main__":
    main()
