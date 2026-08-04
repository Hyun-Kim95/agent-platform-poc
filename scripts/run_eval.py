"""Run heuristic eval against /v1/chat; write data/eval_report.md."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASE = os.environ.get("AGENT_API_BASE", "http://127.0.0.1:8000")
DEFAULT_QUESTIONS = ROOT / "samples" / "eval" / "questions.jsonl"
DEFAULT_REPORT = ROOT / "data" / "eval_report.md"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_questions(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(
                    "bad JSONL line {0}: {1}".format(lineno, exc)
                )
            if not isinstance(obj, dict) or not obj.get("id"):
                raise SystemExit("line {0}: need object with id".format(lineno))
            rows.append(obj)
    return rows


def _citation_types(env: Dict[str, Any]) -> Set[str]:
    out: Set[str] = set()
    for c in env.get("citations") or []:
        t = (c or {}).get("type")
        if t:
            out.add(str(t))
    return out


def score_envelope(
    env: Dict[str, Any], expect: Dict[str, Any]
) -> Tuple[bool, List[str]]:
    """Return (passed, notes)."""
    notes: List[str] = []
    ok = True

    want_status = expect.get("status") or "completed"
    got_status = env.get("status")
    if got_status != want_status:
        ok = False
        notes.append(
            "status want={0} got={1}".format(want_status, got_status)
        )
    else:
        notes.append("status ok")

    want_types = expect.get("citation_types") or []
    if want_types:
        got = _citation_types(env)
        missing = [t for t in want_types if t not in got]
        if missing:
            ok = False
            notes.append(
                "citation_types missing={0} got={1}".format(
                    missing, sorted(got)
                )
            )
        else:
            notes.append("citation_types ok")

    keywords = expect.get("keywords_any") or []
    if keywords:
        answer = (env.get("answer") or "").lower()
        hit = any(str(k).lower() in answer for k in keywords)
        if not hit:
            ok = False
            notes.append("keywords_any miss={0}".format(keywords))
        else:
            notes.append("keywords_any ok")

    return ok, notes


def load_feedback_ratings(path: Path) -> Dict[str, List[int]]:
    """Map run_id -> list of ratings from JSONL (best-effort)."""
    out: Dict[str, List[int]] = {}
    if not path.is_file():
        return out
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = obj.get("run_id")
            try:
                rating = int(obj.get("rating"))
            except (TypeError, ValueError):
                continue
            if not rid:
                continue
            out.setdefault(str(rid), []).append(rating)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Heuristic chat eval")
    parser.add_argument(
        "--questions",
        type=Path,
        default=DEFAULT_QUESTIONS,
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
    )
    parser.add_argument(
        "--with-feedback",
        action="store_true",
        help="Join ratings from FEEDBACK_LOG_PATH JSONL if present",
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args(argv)

    questions = load_questions(args.questions)
    if len(questions) < 1:
        print("ERROR: no questions", file=sys.stderr)
        return 1

    feedback_path = Path(
        os.environ.get(
            "FEEDBACK_LOG_PATH", str(ROOT / "data" / "feedback.jsonl")
        )
    )
    ratings = (
        load_feedback_ratings(feedback_path) if args.with_feedback else {}
    )

    results: List[Dict[str, Any]] = []
    passed = 0

    with httpx.Client(base_url=BASE, timeout=args.timeout) as client:
        for q in questions:
            qid = q["id"]
            body = {
                "tenant_id": q.get("tenant_id") or "internal",
                "query": q.get("query") or "",
            }
            if q.get("engine"):
                body["engine"] = q["engine"]
            try:
                r = client.post("/v1/chat", json=body)
                if r.status_code >= 400:
                    env = {
                        "status": "http_error",
                        "answer": r.text[:500],
                        "citations": [],
                        "run_id": None,
                    }
                    ok = False
                    notes = ["HTTP {0}".format(r.status_code)]
                else:
                    env = r.json()
                    ok, notes = score_envelope(env, q.get("expect") or {})
            except Exception as exc:  # noqa: BLE001
                env = {
                    "status": "error",
                    "answer": str(exc),
                    "citations": [],
                    "run_id": None,
                }
                ok = False
                notes = ["exception: {0}".format(exc)]

            if ok:
                passed += 1
            run_id = env.get("run_id")
            fb = ratings.get(str(run_id), []) if run_id else []
            row = {
                "id": qid,
                "engine": body.get("engine"),
                "ok": ok,
                "status": env.get("status"),
                "run_id": run_id,
                "notes": notes,
                "feedback_ratings": fb,
                "answer_preview": (env.get("answer") or "")[:160],
            }
            results.append(row)
            mark = "PASS" if ok else "FAIL"
            print(
                "{0} {1} engine={2} status={3}".format(
                    mark, qid, body.get("engine"), env.get("status")
                )
            )

    total = len(results)
    lines = [
        "# Eval report",
        "",
        "- generated: `{0}`".format(_utc_now()),
        "- api: `{0}`".format(BASE),
        "- questions: `{0}`".format(args.questions.as_posix()),
        "- score: **{0}/{1}** passed".format(passed, total),
        "",
        "| id | engine | result | status | notes |",
        "|----|--------|--------|--------|-------|",
    ]
    for row in results:
        notes = "; ".join(row["notes"]).replace("|", "/")
        lines.append(
            "| {0} | {1} | {2} | {3} | {4} |".format(
                row["id"],
                row["engine"],
                "PASS" if row["ok"] else "FAIL",
                row["status"],
                notes,
            )
        )
    lines.append("")
    if args.with_feedback:
        lines.append("## Feedback join")
        lines.append("")
        for row in results:
            if row["feedback_ratings"]:
                lines.append(
                    "- `{0}` run_id=`{1}` ratings={2}".format(
                        row["id"], row["run_id"], row["feedback_ratings"]
                    )
                )
        lines.append("")

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("report=", args.report)
    print("summary={0}/{1}".format(passed, total))
    return 0 if passed == total else 2


if __name__ == "__main__":
    raise SystemExit(main())
