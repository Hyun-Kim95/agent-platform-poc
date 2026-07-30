"""Mock tools: calc, clock, faq."""

from __future__ import annotations

import ast
import json
import operator
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FAQ = ROOT / "samples" / "faq.json"

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_UNARY = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _eval_ast(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    # Python 3.9 may still see Num in some paths
    if isinstance(node, ast.Num):  # type: ignore[attr-defined]
        return float(node.n)  # type: ignore[attr-defined]
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return float(_UNARY[type(node.op)](_eval_ast(node.operand)))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left = _eval_ast(node.left)
        right = _eval_ast(node.right)
        return float(_BINOPS[type(node.op)](left, right))
    raise ValueError("unsupported expression")


def extract_math_expr(query: str) -> Optional[str]:
    q = query or ""
    m = re.search(r"([\d\.\s\+\-\*\/\(\)%]+)", q)
    if not m:
        return None
    expr = m.group(1).strip()
    if not re.search(r"\d", expr):
        return None
    if not re.search(r"[\+\-\*\/]", expr):
        return None
    return expr


def run_calc(query: str) -> Tuple[bool, str, Dict[str, Any]]:
    expr = extract_math_expr(query)
    if not expr:
        return False, "no arithmetic expression found", {}
    try:
        tree = ast.parse(expr, mode="eval")
        value = _eval_ast(tree)
    except Exception as exc:  # noqa: BLE001
        return False, "calc error: {0}".format(exc), {"expr": expr}
    text = "{0} = {1}".format(expr, value)
    return True, text, {"expr": expr, "value": value}


def run_clock(_query: str = "") -> Tuple[bool, str, Dict[str, Any]]:
    now_utc = datetime.now(timezone.utc)
    local = now_utc.astimezone()
    text = "UTC {0} / local {1}".format(
        now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        local.isoformat(timespec="seconds"),
    )
    return True, text, {
        "utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "local": local.isoformat(timespec="seconds"),
    }


def _load_faq(path: Path = DEFAULT_FAQ) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return list(raw) if isinstance(raw, list) else []


def run_faq(query: str, path: Path = DEFAULT_FAQ) -> Tuple[bool, str, Dict[str, Any]]:
    q = (query or "").lower()
    items = _load_faq(path)
    for item in items:
        keys = item.get("keywords") or []
        hit = False
        for k in keys:
            ks = str(k)
            if ks.lower() in q or ks in (query or ""):
                hit = True
                break
        if not hit:
            continue
        answer = str(item.get("answer") or "")
        return True, answer, {
            "id": item.get("id"),
            "title": item.get("title") or item.get("id"),
        }
    return False, "no FAQ match", {}


TOOL_RUNNERS = {
    "calc": run_calc,
    "clock": run_clock,
    "faq": run_faq,
}


def run_tool(name: str, query: str) -> Dict[str, Any]:
    fn = TOOL_RUNNERS.get(name)
    if fn is None:
        return {
            "name": name,
            "ok": False,
            "text": "unknown tool",
            "data": {},
        }
    ok, text, data = fn(query)
    return {"name": name, "ok": ok, "text": text, "data": data}
