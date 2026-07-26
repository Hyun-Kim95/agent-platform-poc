"""POST /v1/hitl/{run_id}"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.models import Envelope, HitlRequest, RunStatus
from app.core.orchestrator import Orchestrator

router = APIRouter(prefix="/v1", tags=["hitl"])


def get_orchestrator(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


@router.post("/hitl/{run_id}", response_model=Envelope)
def hitl(run_id: str, body: HitlRequest, request: Request):
    orch = get_orchestrator(request)
    result = orch.hitl(run_id, body)
    if (
        result.error
        and result.error.code == "RUN_NOT_FOUND"
        and result.status == RunStatus.failed
    ):
        return JSONResponse(
            status_code=404, content=result.model_dump(mode="json")
        )
    return result
