"""Descriptive statistics sent to agents. Pure functions; no rounding is applied."""

from __future__ import annotations

import math
from typing import Any


def quantile(sorted_vals: list[float], p: float) -> float:
    """Linear-interpolation quantile (R type 7). p in [0, 1]."""
    if not sorted_vals:
        raise ValueError("empty data")
    if not 0.0 <= p <= 1.0:
        raise ValueError("p must be in [0, 1]")
    h = (len(sorted_vals) - 1) * p
    lo = math.floor(h)
    hi = math.ceil(h)
    return sorted_vals[lo] + (h - lo) * (sorted_vals[hi] - sorted_vals[lo])


def percentile_rank(sorted_vals: list[float], x: float) -> float:
    """Percentage (0-100) of observations <= x."""
    return 100.0 * sum(1 for v in sorted_vals if v <= x) / len(sorted_vals)


def describe(values: list[float], bins: int = 10) -> dict[str, Any]:
    vals = sorted(float(v) for v in values if v is not None and not math.isnan(float(v)))
    if not vals:
        raise ValueError("no numeric values")
    lo, hi = vals[0], vals[-1]
    width = (hi - lo) / bins if hi > lo else 1.0
    counts = [0] * bins
    for v in vals:
        idx = min(int((v - lo) / width), bins - 1) if hi > lo else 0
        counts[idx] += 1
    return {
        "n": len(vals),
        "min": lo,
        "q1": quantile(vals, 0.25),
        "median": quantile(vals, 0.5),
        "q3": quantile(vals, 0.75),
        "max": hi,
        "mean": sum(vals) / len(vals),
        "histogram": [
            {"lower": lo + i * width, "upper": lo + (i + 1) * width, "count": c}
            for i, c in enumerate(counts)
        ],
    }
