"""Optional OpenAI-compatible chat; returns text + TokenUsage."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.config import Settings, get_settings
from app.core.models import TokenUsage
from app.llm.usage import estimate_usage, usage_from_openai_response


class LlmError(Exception):
    pass


def chat_completion(
    messages: List[Dict[str, str]],
    *,
    settings: Optional[Settings] = None,
    temperature: float = 0.0,
) -> Tuple[str, TokenUsage]:
    """Call chat/completions. Raises LlmError if key missing or HTTP fails."""
    cfg = settings or get_settings()
    if not (cfg.llm_api_key or "").strip():
        raise LlmError("LLM_API_KEY is empty")

    url = cfg.llm_base_url.rstrip("/") + "/chat/completions"
    payload: Dict[str, Any] = {
        "model": cfg.llm_model,
        "messages": messages,
        "temperature": temperature,
    }
    headers = {
        "Authorization": "Bearer {0}".format(cfg.llm_api_key),
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=60.0) as client:
        r = client.post(url, json=payload, headers=headers)
        if r.status_code >= 400:
            raise LlmError(
                "LLM HTTP {0}: {1}".format(r.status_code, r.text[:300])
            )
        data = r.json()

    text = ""
    choices = data.get("choices") or []
    if choices:
        msg = (choices[0] or {}).get("message") or {}
        text = msg.get("content") or ""

    usage = usage_from_openai_response(data, model=cfg.llm_model)
    if usage is None:
        prompt = "\n".join(m.get("content") or "" for m in messages)
        usage = estimate_usage(prompt, text, cfg.llm_model)
    return text, usage
