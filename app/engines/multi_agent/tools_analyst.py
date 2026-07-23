"""CSV analyst helpers (stdlib csv only)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional, Tuple

from app.core.config import ROOT


def sum_revenue(data_path: str) -> Tuple[Optional[float], str]:
    path = Path(data_path)
    if not path.is_file():
        path = ROOT / data_path
    if not path.is_file():
        return None, "CSV not found: {0}".format(data_path)

    total = 0.0
    rows = 0
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "revenue" not in reader.fieldnames:
            return None, "CSV missing revenue column"
        for row in reader:
            try:
                total += float(row.get("revenue") or 0)
                rows += 1
            except ValueError:
                continue

    summary = "rows={0}, revenue_sum={1}".format(rows, total)
    return total, summary
