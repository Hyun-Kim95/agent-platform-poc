"""Shared state for multi_agent LangGraph pipeline."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class AgentState(TypedDict, total=False):
    query: str
    data_path: str
    rules_only: bool
    hitl_enabled: bool
    force_reviewer_insufficient: bool
    max_iterations: int
    iteration: int
    error_code: Optional[str]
    route: str
    web_hits: List[Dict[str, Any]]
    web_search_source: str  # tavily | mock
    data_summary: str
    data_value: Optional[float]
    citations: List[Dict[str, Any]]
    # Past tool rounds archived before clear (loop retries). Not Envelope citations.
    citation_history: List[Dict[str, Any]]
    draft: str
    risks: List[str]
    answer: str
    ok: bool
    revise_target: Optional[str]
    last_feedback: Optional[str]
    last_revise_target: Optional[str]
