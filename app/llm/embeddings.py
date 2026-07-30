"""OpenAI-compatible embeddings API."""

from __future__ import annotations

from typing import List, Optional, Tuple

import httpx

from app.core.config import Settings, get_settings
from app.core.models import TokenUsage
from app.llm.client import LlmError
from app.llm.usage import estimate_usage, usage_from_openai_response


def embed_texts(
    texts: List[str],
    *,
    settings: Optional[Settings] = None,
) -> Tuple[List[List[float]], TokenUsage]:
    """Return (vectors, usage). Raises LlmError on missing key / HTTP error."""
    cfg = settings or get_settings()
    if not (cfg.llm_api_key or "").strip():
        raise LlmError("LLM_API_KEY is empty")
    if not texts:
        return [], estimate_usage("", "", cfg.embedding_model)

    url = cfg.llm_base_url.rstrip("/") + "/embeddings"
    payload = {
        "model": cfg.embedding_model,
        "input": texts,
    }
    headers = {
        "Authorization": "Bearer {0}".format(cfg.llm_api_key),
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=120.0) as client:
        r = client.post(url, json=payload, headers=headers)
        if r.status_code >= 400:
            raise LlmError(
                "Embedding HTTP {0}: {1}".format(r.status_code, r.text[:300])
            )
        data = r.json()

    items = sorted(data.get("data") or [], key=lambda x: x.get("index", 0))
    vectors = [list(it.get("embedding") or []) for it in items]
    if len(vectors) != len(texts):
        raise LlmError("embedding count mismatch")

    usage = usage_from_openai_response(data, model=cfg.embedding_model)
    if usage is None:
        usage = estimate_usage("\n".join(texts), "", cfg.embedding_model)
    return vectors, usage
