"""POST /v1/chat"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.models import ChatRequest, Envelope
from app.core.orchestrator import Orchestrator

router = APIRouter(prefix="/v1", tags=["chat"])


def get_orchestrator(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


@router.post("/chat", response_model=Envelope)
def chat(body: ChatRequest, request: Request) -> Envelope:
    orch = get_orchestrator(request)
    return orch.chat(body)
