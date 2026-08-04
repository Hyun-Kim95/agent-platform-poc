"""Unit smoke for Stretch S3: chunk strategy, collection, token rerank."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.engines.hybrid_rag.rag import (
    DOCS_DIR,
    chunk_document,
    chunk_strategy_name,
    iter_doc_files,
    rerank_token_overlap,
    retrieve_keyword,
)


def main() -> int:
    files = iter_doc_files()
    assert files, "expected docs under samples/docs"
    colls = {c for _p, c in files}
    assert "general" in colls or "policy" in colls or "default" in colls, colls
    print("OK collections", sorted(colls))

    sample = None
    for path, coll in files:
        if path.name == "refund_policy.md":
            sample = path
            break
    if sample is None:
        sample = files[0][0]

    heading = chunk_document(sample, chunk_size=0, chunk_overlap=0)
    windowed = chunk_document(sample, chunk_size=80, chunk_overlap=20)
    assert chunk_strategy_name(0) == "heading"
    assert chunk_strategy_name(80) == "heading_char"
    assert len(windowed) >= len(heading), (len(heading), len(windowed))
    print(
        "OK chunks heading={0} heading_char={1}".format(
            len(heading), len(windowed)
        )
    )

    passages = [
        {
            "text": "배송은 당일 출고",
            "citation": {"ref": "a"},
        },
        {
            "text": "환불은 7일 이내 전액 환불 가능",
            "citation": {"ref": "b"},
        },
        {
            "text": "해외 배송 견적",
            "citation": {"ref": "c"},
        },
    ]
    ranked = rerank_token_overlap("환불 7일", passages, top_k=2)
    assert ranked[0]["citation"]["ref"] == "b", ranked
    assert ranked[0]["score"] >= ranked[1]["score"]
    print("OK rerank", [p["citation"]["ref"] for p in ranked])

    if (DOCS_DIR / "policy").is_dir():
        only = retrieve_keyword(
            "환불",
            top_k=5,
            collection="policy",
            chunk_size=0,
        )
        assert only, "policy collection should hit refund docs"
        assert all(p.get("collection") == "policy" for p in only), only
        print("OK keyword collection filter n=", len(only))

    print("smoke_rag_s3: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
