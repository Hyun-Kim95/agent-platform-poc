"""Persist HITL checkpoint across compiled-graph rebuild + checkpointer reopen."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langgraph.types import Command

from app.core.config import get_settings
from app.engines.multi_agent.checkpoint import (
    checkpoint_backend,
    get_checkpointer,
    reset_checkpointer,
)
from app.engines.multi_agent.graph import (
    build_graph,
    reset_compiled_graph,
    thread_config,
)


def main() -> int:
    cfg = get_settings()
    reset_compiled_graph()
    reset_checkpointer()

    cp1 = get_checkpointer(cfg)
    print("backend=", checkpoint_backend())
    g1 = build_graph().compile(checkpointer=cp1)

    rid = "run_ckpt_{0}".format(uuid.uuid4().hex[:12])
    conf = thread_config(rid)
    initial = {
        "query": "checkpoint smoke hello",
        "data_path": "samples/mini.csv",
        "rules_only": True,
        "hitl_enabled": True,
        "force_reviewer_insufficient": False,
        "max_iterations": 8,
        "iteration": 0,
        "error_code": None,
        "citations": [],
        "citation_history": [],
        "risks": [],
        "ok": True,
    }
    g1.invoke(initial, conf)
    snap1 = g1.get_state(conf)
    assert snap1.next, "expected interrupt waiting at human, got next={0}".format(
        snap1.next
    )
    print("OK interrupt next=", snap1.next)

    # Simulate process restart: drop graph + reopen checkpointer from same DB.
    reset_compiled_graph()
    reset_checkpointer()
    cp2 = get_checkpointer(cfg)
    g2 = build_graph().compile(checkpointer=cp2)
    snap2 = g2.get_state(conf)
    assert snap2.next, "checkpoint lost after reopen, next={0}".format(snap2.next)
    print("OK restored next=", snap2.next)

    g2.invoke(Command(resume={"decision": "approve"}), conf)
    snap3 = g2.get_state(conf)
    assert not snap3.next, "expected finished graph, next={0}".format(snap3.next)
    values = dict(snap3.values or {})
    assert (values.get("answer") or "").strip(), values
    print("OK resumed answer=", (values.get("answer") or "")[:80])
    print("smoke_checkpoint: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
