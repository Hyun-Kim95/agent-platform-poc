"""Token/cost helpers: heuristic estimate + rough USD rates."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.models import TokenUsage

# Learning-only list prices (USD / 1K tokens). Not a billing SSOT.
_RATES_PER_1K = {
    "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006},
    "gpt-4o": {"prompt": 0.0025, "completion": 0.01},
}
_DEFAULT_RATE = {"prompt": 0.00015, "completion": 0.0006}


def estimate_tokens(text: str) -> int:
    """Rough char/4 heuristic for mixed KO/EN (learning)."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def estimate_cost_usd(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    rates = _RATES_PER_1K.get(model, _DEFAULT_RATE)
    cost = (
        prompt_tokens / 1000.0 * rates["prompt"]
        + completion_tokens / 1000.0 * rates["completion"]
    )
    return round(cost, 8)


def estimate_usage(
    prompt: str,
    completion: str,
    model: str,
) -> TokenUsage:
    pt = estimate_tokens(prompt)
    ct = estimate_tokens(completion or "")
    return TokenUsage(
        prompt_tokens=pt,
        completion_tokens=ct,
        total_tokens=pt + ct,
        model=model or "",
        estimated=True,
        cost_usd=estimate_cost_usd(model, pt, ct),
    )


def usage_from_provider(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    model: str,
) -> TokenUsage:
    pt = max(0, int(prompt_tokens))
    ct = max(0, int(completion_tokens))
    return TokenUsage(
        prompt_tokens=pt,
        completion_tokens=ct,
        total_tokens=pt + ct,
        model=model or "",
        estimated=False,
        cost_usd=estimate_cost_usd(model, pt, ct),
    )


def usage_from_openai_response(
    data: Dict[str, Any],
    *,
    model: str,
) -> Optional[TokenUsage]:
    usage = data.get("usage") or {}
    if not usage:
        return None
    return usage_from_provider(
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        model=str(data.get("model") or model),
    )


def merge_usage(
    a: Optional[TokenUsage],
    b: Optional[TokenUsage],
) -> Optional[TokenUsage]:
    if a is None:
        return b
    if b is None:
        return a
    pt = a.prompt_tokens + b.prompt_tokens
    ct = a.completion_tokens + b.completion_tokens
    model = b.model or a.model
    estimated = a.estimated or b.estimated
    return TokenUsage(
        prompt_tokens=pt,
        completion_tokens=ct,
        total_tokens=pt + ct,
        model=model,
        estimated=estimated,
        cost_usd=estimate_cost_usd(model, pt, ct),
    )
