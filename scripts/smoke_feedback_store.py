"""Unit smoke FeedbackStore: postgres if URL up, else jsonl."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.feedback.store import FeedbackStore


def main() -> int:
    cfg = get_settings()
    store = FeedbackStore(settings=cfg)
    print("backend=", store.backend)

    run_id = "run_fb_smoke_{0}".format(uuid.uuid4().hex[:12])
    saved = store.append(
        run_id=run_id,
        rating=4,
        comment="unit smoke",
        labels=["smoke", "a"],
    )
    assert saved["feedback_id"].startswith("fb_")
    assert saved["rating"] == 4

    got = store.get(saved["feedback_id"])
    assert got is not None, "missing feedback row"
    assert got["run_id"] == run_id
    assert got["rating"] == 4
    assert "smoke" in (got.get("labels") or [])
    print("smoke_feedback_store: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
