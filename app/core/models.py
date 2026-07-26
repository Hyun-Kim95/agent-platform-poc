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
    type: Literal["web", "data", "no_hit"]
    ref: str = ""
    title: str = ""
    snippet: Optional[str] = None


class Meta(BaseModel):
    engine: str
    tenant_id: str
    latency_ms: int = 0
    timeout_ms: int = 120_000
    thread_id: Optional[str] = None
    route: Optional[Literal["web", "data", "both", "clarify"]] = None


class ErrorObject(BaseModel):
    code: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class HitlPreview(BaseModel):
    summary: str = ""
    risks: List[str] = Field(default_factory=list)


HitlAction = Literal["approve", "revise", "reject"]


class HitlView(BaseModel):
    required: bool = True
    actions: List[HitlAction] = Field(
        default_factory=lambda: ["approve", "revise", "reject"]
    )
    preview: Optional[HitlPreview] = None


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
