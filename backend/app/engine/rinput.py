"""Assembles the R input from a stored decision. Values are copied through untouched."""

from __future__ import annotations

from typing import Any


def build_r_input(
    decision: dict[str, Any],
    data: dict[str, list[float]],
    directions: dict[str, str],
    dir_exp: dict[str, int | None],
    outcome: str,
) -> dict[str, Any]:
    conds = [
        {
            "name": name,
            "direction": directions[name],
            "dir_exp": dir_exp.get(name),
            "anchors": block["anchors"],
        }
        for name, block in decision["conditions"].items()
    ]
    return {
        "data": data,
        "conditions": conds,
        "outcome": {"name": outcome, "direction": directions[outcome], "anchors": decision["outcome"]["anchors"]},
        "truth_table": {k: decision["truth_table"].get(k) for k in ("consistency_threshold", "frequency_threshold", "pri_threshold")},
    }
