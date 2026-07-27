"""POST /v1/feedback — AC-F01~F03 / D009."""

from __future__ import annotations

from typing import Union

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.models import (
    ErrorObject,
    FeedbackErrorBody,
    FeedbackRequest,
    FeedbackResponse,
)
from app.core.orchestrator import Orchestrator

router = APIRouter(prefix="/v1", tags=["feedback"])


def get_orchestrator(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


@router.post("/feedback", response_model=FeedbackResponse)
def feedback(
    body: FeedbackRequest, request: Request
) -> Union[FeedbackResponse, JSONResponse]:
    orch = get_orchestrator(request)
    result = orch.submit_feedback(body)
    if isinstance(result, ErrorObject):
        payload = FeedbackErrorBody(ok=False, error=result)
        return JSONResponse(
            status_code=404,
            content=payload.model_dump(mode="json"),
        )
    return result
