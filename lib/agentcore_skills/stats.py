"""Percentiles and latency summaries that two different scripts must agree on.

`trace_report.py` (exported X-Ray traces) and `verify.py` (live probes) both
judge a p50/p95 against the same budget, so they share one definition:
nearest-rank on the sorted samples, which never invents a value that was not
measured. With fewer than 20 samples a p95 is just the maximum, and the
summary says so rather than implying precision it does not have.
"""

from __future__ import annotations

import math
from typing import Iterable


def percentile(values: Iterable[float], pct: float) -> float | None:
    data = sorted(float(v) for v in values)
    if not data:
        return None
    if pct <= 0:
        return data[0]
    rank = math.ceil(pct / 100.0 * len(data))
    return data[min(max(rank, 1), len(data)) - 1]


def summarize(values: Iterable[float], *, budget_ms: float | None = None) -> dict:
    data = sorted(float(v) for v in values)
    out: dict = {"count": len(data)}
    if not data:
        return out
    out.update({
        "min_ms": round(data[0], 2),
        "p50_ms": round(percentile(data, 50), 2),
        "p95_ms": round(percentile(data, 95), 2),
        "max_ms": round(data[-1], 2),
        "mean_ms": round(sum(data) / len(data), 2),
    })
    if len(data) < 20:
        out["note"] = f"{len(data)} sample(s): p95 is effectively the maximum"
    if budget_ms is not None:
        over = sum(1 for v in data if v > budget_ms)
        out["budget_ms"] = budget_ms
        out["over_budget"] = over
        out["over_budget_pct"] = round(100.0 * over / len(data), 1)
    return out
