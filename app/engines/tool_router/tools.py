"""Tools: calc/clock/faq (local) + fetch (real HTTP GET)."""

from __future__ import annotations

import ast
import ipaddress
import json
import operator
import re
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

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

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)
_FETCH_MAX_BYTES = 64_000
_FETCH_TIMEOUT = 10.0


def _eval_ast(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
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
    """Pull a simple arithmetic expression; ignore URL path slashes."""
    q = query or ""
    # Strip URLs first so ``http://127.0.0.1/`` is not treated as ``127.0.0.1/``.
    q = _URL_RE.sub(" ", q)
    m = re.search(r"([\d\.\s\+\-\*\/\(\)%]+)", q)
    if not m:
        return None
    expr = m.group(1).strip()
    if not re.search(r"\d", expr):
        return None
    # Require a real operator. Lone ``/`` (from paths) is not enough; allow ``a/b``.
    if not (
        re.search(r"[\+\-\*]", expr) or re.search(r"\d\s*/\s*\d", expr)
    ):
        return None
    return expr


def extract_url(query: str) -> Optional[str]:
    m = _URL_RE.search(query or "")
    if not m:
        return None
    return m.group(0).rstrip(".,;:)")


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


def _host_blocked(hostname: str) -> bool:
    host = (hostname or "").strip().lower().rstrip(".")
    if not host:
        return True
    if host in ("localhost", "localhost.localdomain"):
        return True
    if host.endswith(".local") or host.endswith(".internal"):
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True
    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return True
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return True
    return False


def run_fetch(query: str) -> Tuple[bool, str, Dict[str, Any]]:
    url = extract_url(query)
    if not url:
        return False, "no http(s) URL found in query", {}
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, "only http/https allowed", {"url": url}
    if not parsed.hostname:
        return False, "URL missing host", {"url": url}
    if _host_blocked(parsed.hostname):
        return False, "blocked host (SSRF guard)", {"url": url}

    try:
        with httpx.Client(
            timeout=_FETCH_TIMEOUT,
            follow_redirects=False,
            headers={"User-Agent": "agent-platform-poc-fetch/0.1"},
        ) as client:
            resp = client.get(url)
    except Exception as exc:  # noqa: BLE001
        return False, "fetch error: {0}".format(exc), {"url": url}

    if resp.status_code >= 400:
        return (
            False,
            "HTTP {0}".format(resp.status_code),
            {"url": url, "status": resp.status_code},
        )

    raw = resp.content[:_FETCH_MAX_BYTES]
    ctype = (resp.headers.get("content-type") or "").split(";")[0].strip()
    try:
        text_body = raw.decode(resp.encoding or "utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        text_body = raw.decode("utf-8", errors="replace")

    title = ""
    m = re.search(
        r"<title[^>]*>(.*?)</title>", text_body, re.IGNORECASE | re.DOTALL
    )
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()[:120]

    plain = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text_body)
    plain = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", plain)
    plain = re.sub(r"(?s)<[^>]+>", " ", plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    excerpt = plain[:500]

    summary = "URL {0}".format(url)
    if title:
        summary += " | title: {0}".format(title)
    if excerpt:
        summary += " | {0}".format(excerpt)
    else:
        summary += " | (empty body, content-type={0})".format(ctype or "?")

    return True, summary, {
        "url": url,
        "status": resp.status_code,
        "content_type": ctype,
        "title": title,
        "bytes": len(raw),
    }


TOOL_RUNNERS = {
    "calc": run_calc,
    "clock": run_clock,
    "faq": run_faq,
    "fetch": run_fetch,
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
