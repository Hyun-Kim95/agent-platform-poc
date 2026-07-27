"""Shared state for multi_agent LangGraph pipeline."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class AgentState(TypedDict, total=False):
    query: str
    data_path: str
    rules_only: bool
    hitl_enabled: bool
    route: str
    web_hits: List[Dict[str, Any]]
    data_summary: str
    data_value: Optional[float]
    citations: List[Dict[str, Any]]
    draft: str
    risks: List[str]
    answer: str
    ok: bool
    revise_target: Optional[str]
