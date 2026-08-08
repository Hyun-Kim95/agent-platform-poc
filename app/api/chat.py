"""POST /v1/chat and POST /v1/chat/stream."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.sse_util import format_sse
from app.core.models import ChatRequest, Envelope
from app.core.orchestrator import Orchestrator

router = APIRouter(prefix="/v1", tags=["chat"])


def get_orchestrator(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


@router.post("/chat", response_model=Envelope)
def chat(body: ChatRequest, request: Request) -> Envelope:
    orch = get_orchestrator(request)
    return orch.chat(body)


@router.post("/chat/stream")
def chat_stream(body: ChatRequest, request: Request) -> StreamingResponse:
    orch = get_orchestrator(request)

    def gen():
        try:
            for event, data in orch.chat_stream(body):
                yield format_sse(event, data)
        except Exception as exc:
            yield format_sse(
                "error",
                {"code": "INTERNAL", "message": str(exc)[:500]},
            )
            yield format_sse("done", {})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
