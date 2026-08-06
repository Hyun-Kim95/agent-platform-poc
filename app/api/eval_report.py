"""GET /v1/eval/report — read data/eval_report.md for /ui."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.config import ROOT

router = APIRouter(prefix="/v1", tags=["eval"])

DEFAULT_REPORT = ROOT / "data" / "eval_report.md"
_SCORE_RE = re.compile(r"score:\s*\*\*(\d+)\s*/\s*(\d+)\*\*", re.I)
_GEN_RE = re.compile(r"generated:\s*`([^`]+)`", re.I)


class EvalReportSummary(BaseModel):
    generated: Optional[str] = None
    passed: Optional[int] = None
    total: Optional[int] = None
    score_label: Optional[str] = None


class EvalReportResponse(BaseModel):
    ok: bool = True
    path: str = "data/eval_report.md"
    exists: bool = True
    summary: EvalReportSummary = Field(default_factory=EvalReportSummary)
    markdown: str = ""
    rows_preview: List[str] = Field(default_factory=list)


class EvalReportError(BaseModel):
    ok: bool = False
    error: Dict[str, Any]


def _parse_summary(text: str) -> EvalReportSummary:
    generated = None
    m = _GEN_RE.search(text)
    if m:
        generated = m.group(1)
    passed = total = None
    score_label = None
    sm = _SCORE_RE.search(text)
    if sm:
        passed = int(sm.group(1))
        total = int(sm.group(2))
        score_label = "{0}/{1}".format(passed, total)
    return EvalReportSummary(
        generated=generated,
        passed=passed,
        total=total,
        score_label=score_label,
    )


def _table_preview(text: str, limit: int = 12) -> List[str]:
    lines = []
    in_table = False
    for line in text.splitlines():
        if line.startswith("| id "):
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                break
            if re.match(r"^\|\s*-+", line):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 3:
                lines.append(
                    "{0} · {1} · {2}".format(cells[0], cells[1], cells[2])
                )
            if len(lines) >= limit:
                break
    return lines


@router.get(
    "/eval/report",
    response_model=EvalReportResponse,
    responses={404: {"model": EvalReportError}},
)
def get_eval_report() -> Any:
    path = DEFAULT_REPORT
    if not path.is_file():
        return JSONResponse(
            status_code=404,
            content={
                "ok": False,
                "error": {
                    "code": "EVAL_REPORT_NOT_FOUND",
                    "message": (
                        "data/eval_report.md missing — "
                        "run: python scripts/run_eval.py"
                    ),
                    "details": {},
                },
            },
        )
    text = path.read_text(encoding="utf-8")
    return EvalReportResponse(
        path="data/eval_report.md",
        exists=True,
        summary=_parse_summary(text),
        markdown=text,
        rows_preview=_table_preview(text),
    )
