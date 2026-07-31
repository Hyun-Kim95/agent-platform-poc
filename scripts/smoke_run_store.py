"""Smoke RunStore: postgres if URL up, else sqlite (nested graph_state)."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.store.run_store import RunRecord, RunStore


def main() -> int:
    cfg = get_settings()
    store = RunStore(settings=cfg)
    print("backend=", store.backend)

    rid = "run_smoke_jsonb_{0}".format(uuid.uuid4().hex[:12])
    now = RunStore.now()
    nested = {
        "query": "jsonb smoke",
        "k": 1,
        "agent_state": {"route": "both", "hits": [{"n": 1}]},
    }
    store.save(
        RunRecord(
            run_id=rid,
            status="waiting_human",
            graph_state=nested,
            tenant_id="demo",
            engine="multi_agent",
            thread_id=None,
            created_at=now,
            updated_at=now,
            error_code=None,
        )
    )
    got = store.get(rid)
    assert got is not None, "missing row"
    assert got.status == "waiting_human"
    assert got.graph_state.get("k") == 1
    assert got.graph_state.get("agent_state", {}).get("route") == "both"
    assert got.graph_state["agent_state"]["hits"][0]["n"] == 1
    assert got.engine == "multi_agent"

    later = RunStore.now()
    store.save(
        RunRecord(
            run_id=rid,
            status="completed",
            graph_state={
                "query": "jsonb smoke",
                "k": 2,
                "agent_state": {"route": "data", "hits": []},
            },
            tenant_id="demo",
            engine="multi_agent",
            thread_id=None,
            created_at=now,
            updated_at=later,
            error_code=None,
        )
    )
    got2 = store.get(rid)
    assert got2 is not None
    assert got2.status == "completed"
    assert got2.graph_state.get("k") == 2
    assert got2.graph_state.get("agent_state", {}).get("route") == "data"
    print("smoke_run_store: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
