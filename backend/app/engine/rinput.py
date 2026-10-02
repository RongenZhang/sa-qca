"""Assembles the R input from a stored decision. Values are copied through untouched."""

from __future__ import annotations

from typing import Any


def _calibration(kind: str, block: dict[str, Any] | None) -> dict[str, Any]:
    if kind == "precalibrated":
        return {"calibration": {"kind": "precalibrated"}}
    if block is None:
        raise ValueError("a variable that must be calibrated is missing from the decision")
    if kind == "breakpoints":
        return {"calibration": {"kind": "breakpoints", "breakpoints": block["breakpoints"]}}
    return {"anchors": block["anchors"]}  # direct: the original input shape, so earlier runs stay byte-identical


def build_r_input(
    decision: dict[str, Any],
    data: dict[str, list[float]],
    directions: dict[str, str],
    dir_exp: dict[str, int | None],
    outcome: str,
    kinds: dict[str, str] | None = None,
    condition_order: list[str] | None = None,
) -> dict[str, Any]:
    """`kinds` maps a variable to "direct" (default), "breakpoints" or "precalibrated". Pre-calibrated conditions are
    not in the decision (they are fixed); they are passed to R as already-calibrated memberships. `condition_order`
    lists every condition, calibrated or not (default: the decision's own order)."""
    kinds = kinds or {}
    order = condition_order or list(decision["conditions"])
    conds = [
        {
            "name": name,
            "direction": directions[name],
            "dir_exp": dir_exp.get(name),
            **_calibration(kinds.get(name, "direct"), decision["conditions"].get(name)),
        }
        for name in order
    ]
    return {
        "data": data,
        "conditions": conds,
        "outcome": {"name": outcome, "direction": directions[outcome], **_calibration(kinds.get(outcome, "direct"), decision["outcome"])},
        "truth_table": {k: decision["truth_table"].get(k) for k in ("consistency_threshold", "frequency_threshold", "pri_threshold")},
    }
