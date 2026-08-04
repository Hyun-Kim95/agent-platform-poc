"""API request/response envelope models."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class RunStatus(str, Enum):
    completed = "completed"
    waiting_human = "waiting_human"
    failed = "failed"


class Citation(BaseModel):
    type: Literal["web", "data", "doc", "sql", "tool", "no_hit"]
    ref: str = ""
    title: str = ""
    snippet: Optional[str] = None


class TokenUsage(BaseModel):
    """LLM token/cost snapshot (estimated or provider-reported)."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    estimated: bool = True
    cost_usd: Optional[float] = None


class Meta(BaseModel):
    engine: str
    tenant_id: str
    latency_ms: int = 0
    timeout_ms: int = 120_000
    thread_id: Optional[str] = None
    route: Optional[
        Literal[
            "web",
            "data",
            "both",
            "clarify",
            "rag",
            "sql",
            "calc",
            "clock",
            "faq",
            "fetch",
            "none",
        ]
    ] = None
    usage: Optional[TokenUsage] = None
    rag_source: Optional[Literal["vector", "keyword", "none"]] = None
    sql_backend: Optional[Literal["postgres", "sqlite"]] = None
    web_search_source: Optional[Literal["tavily", "mock"]] = None
    rag_collection: Optional[str] = None
    chunk_strategy: Optional[Literal["heading", "heading_char"]] = None
    rag_rerank: Optional[Literal["none", "token_overlap"]] = None


class ErrorObject(BaseModel):
    code: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class HitlPreview(BaseModel):
    """HITL draft preview. summary stays Data-first plain text (compat)."""

    summary: str = ""
    risks: List[str] = Field(default_factory=list)
    route: Optional[str] = None
    data_summary: Optional[str] = None
    web_titles: List[str] = Field(default_factory=list)
    last_feedback: Optional[str] = None
    last_revise_target: Optional[str] = None


HitlAction = Literal["approve", "revise", "reject"]


class HitlView(BaseModel):
    required: bool = True
    actions: List[HitlAction] = Field(
        default_factory=lambda: ["approve", "revise", "reject"]
    )
    preview: Optional[HitlPreview] = None
    last_feedback: Optional[str] = None
    last_revise_target: Optional[str] = None


class ChatRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    engine: Optional[str] = None
    query: str = Field(min_length=1, max_length=8000)
    thread_id: Optional[str] = Field(default=None, max_length=128)


class HitlRequest(BaseModel):
    decision: Literal["approve", "revise", "reject"]
    feedback: Optional[str] = Field(default=None, max_length=4000)
    revise_target: Optional[Literal["search", "analyst"]] = None

    @model_validator(mode="after")
    def revise_needs_feedback(self) -> "HitlRequest":
        if self.decision == "revise":
            fb = (self.feedback or "").strip()
            if not fb:
                raise ValueError("feedback is required when decision=revise")
            self.feedback = fb
        return self


class FeedbackRequest(BaseModel):
    """POST /v1/feedback body."""

    run_id: str = Field(min_length=1, max_length=128)
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = Field(default=None, max_length=4000)
    labels: List[str] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def normalize_labels(self) -> "FeedbackRequest":
        cleaned: List[str] = []
        for raw in self.labels:
            s = (raw or "").strip()
            if not s:
                continue
            if len(s) > 64:
                raise ValueError("each label must be at most 64 chars")
            cleaned.append(s)
        self.labels = cleaned
        if self.comment is not None:
            self.comment = self.comment.strip() or None
        return self


class FeedbackResponse(BaseModel):
    ok: bool = True
    feedback_id: str
    run_id: str
    stored_at: str


class FeedbackErrorBody(BaseModel):
    """404 body for missing run (not the chat Envelope)."""

    ok: bool = False
    error: ErrorObject


class Envelope(BaseModel):
    """Shared response for /v1/chat and /v1/hitl."""

    trace_id: str
    run_id: str
    status: RunStatus
    answer: Optional[str]
    citations: List[Citation] = Field(default_factory=list)
    meta: Meta
    error: Optional[ErrorObject] = None
    hitl: Optional[HitlView] = None


class EngineContext(BaseModel):
    """Runtime context passed into AgentEngine.run / resume."""

    tenant_id: str
    query: str
    thread_id: Optional[str]
    trace_id: str
    run_id: str
    timeout_ms: int
    hitl_enabled: bool
    max_iterations: int = 8
    data_path: str = "samples/mini.csv"
    rules_only: bool = False
    force_reviewer_insufficient: bool = False
