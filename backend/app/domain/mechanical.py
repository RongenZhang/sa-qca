"""Mechanical arm: conventional percentile perturbation of the analyst's original specification.

Deterministic grid (no randomness). Parameters are PROVISIONAL defaults, not verified against
Skaaning (2011); they are configurable and recorded with every run.
Each perturbation is applied to all variables jointly unless kind == "crossover_one".
Configurations whose perturbed anchors would break ordering are returned as skipped with a
reason, never repaired.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.schema import ANCHOR_KEYS
from app.domain.stats import percentile_rank, quantile


@dataclass(frozen=True)
class MechanicalParams:
    percentile_shifts: tuple[float, ...] = (-10.0, -5.0, 5.0, 10.0)
    crossover_nudges: tuple[float, ...] = (-10.0, -5.0, 5.0, 10.0)
    consistency_shifts: tuple[float, ...] = (-0.05, 0.05)
    frequency_shifts: tuple[int, ...] = (-1, 1)


@dataclass
class MechanicalConfig:
    id: str
    description: str
    decision: dict[str, Any] | None
    skipped_reason: str | None = None
    perturbation: dict[str, Any] = field(default_factory=dict)


def _shift_anchor(sorted_vals: list[float], x: float, shift: float) -> float:
    rank = percentile_rank(sorted_vals, x) + shift
    rank = min(100.0, max(0.0, rank))  # rank bound on the percentile scale, not on raw anchors
    return quantile(sorted_vals, rank / 100.0)


def _ordered(a: dict[str, float], direction: str) -> bool:
    fn, cr, fm = (a[k] for k in ANCHOR_KEYS)
    return fn < cr < fm if direction == "positive" else fn > cr > fm


def generate_mechanical_configs(
    data: dict[str, list[float]],
    reference: dict[str, dict[str, float]],
    directions: dict[str, str],
    outcome: str,
    ref_cutoffs: dict[str, Any],
    params: MechanicalParams = MechanicalParams(),
) -> list[MechanicalConfig]:
    names = [n for n in reference if n != outcome]
    sorted_data = {n: sorted(float(v) for v in data[n]) for n in [*names, outcome]}

    def build(anchor_map: dict[str, dict[str, float]], tt: dict[str, Any], note: str) -> dict[str, Any]:
        def block(n: str) -> dict[str, Any]:
            return {
                "anchors": anchor_map[n],
                "rationale": {k: f"mechanical: {note}" for k in ANCHOR_KEYS},
            }

        return {
            "conditions": {n: block(n) for n in names},
            "outcome": block(outcome),
            "truth_table": tt,
        }

    def cutoffs(**over: Any) -> dict[str, Any]:
        tt = {
            "consistency_threshold": ref_cutoffs["consistency_threshold"],
            "frequency_threshold": ref_cutoffs["frequency_threshold"],
            "pri_threshold": ref_cutoffs.get("pri_threshold"),
            "consistency_rationale": "mechanical: reference cutoff",
            "frequency_rationale": "mechanical: reference cutoff",
            "pri_rationale": "mechanical: reference cutoff" if ref_cutoffs.get("pri_threshold") is not None else None,
        }
        tt.update(over)
        return tt

    def shifted(shift_fn: Any) -> dict[str, dict[str, float]]:
        return {n: shift_fn(n) for n in [*names, outcome]}

    configs: list[MechanicalConfig] = []

    def add(cid: str, desc: str, anchor_map: dict[str, dict[str, float]], tt: dict[str, Any], pert: dict[str, Any]) -> None:
        bad = [n for n, a in anchor_map.items() if not _ordered(a, directions[n])]
        if bad:
            configs.append(MechanicalConfig(cid, desc, None, f"ordering broken for: {', '.join(bad)}", pert))
        else:
            configs.append(MechanicalConfig(cid, desc, build(anchor_map, tt, desc), None, pert))

    for s in params.percentile_shifts:
        add(
            f"joint_shift_{s:+g}",
            f"all anchors shifted {s:+g} percentile points",
            shifted(lambda n, s=s: {k: _shift_anchor(sorted_data[n], reference[n][k], s) for k in ANCHOR_KEYS}),
            cutoffs(),
            {"kind": "joint_shift", "shift": s},
        )
    for s in params.crossover_nudges:
        add(
            f"crossover_all_{s:+g}",
            f"all crossovers shifted {s:+g} percentile points",
            shifted(lambda n, s=s: {**reference[n], "crossover": _shift_anchor(sorted_data[n], reference[n]["crossover"], s)}),
            cutoffs(),
            {"kind": "crossover_all", "shift": s},
        )
    for target in [*names, outcome]:
        for s in params.crossover_nudges:
            add(
                f"crossover_one_{target}_{s:+g}",
                f"crossover of {target} shifted {s:+g} percentile points",
                shifted(
                    lambda n, s=s, target=target: (
                        {**reference[n], "crossover": _shift_anchor(sorted_data[n], reference[n]["crossover"], s)}
                        if n == target
                        else dict(reference[n])
                    )
                ),
                cutoffs(),
                {"kind": "crossover_one", "variable": target, "shift": s},
            )
    ref_anchors = {n: dict(reference[n]) for n in [*names, outcome]}
    for d in params.consistency_shifts:
        val = round(ref_cutoffs["consistency_threshold"] + d, 10)  # generator arithmetic, not agent output
        if 0.0 <= val <= 1.0:
            add(f"consistency_{d:+g}", f"consistency cutoff {d:+g}", ref_anchors, cutoffs(consistency_threshold=val), {"kind": "consistency", "shift": d})
        else:
            configs.append(MechanicalConfig(f"consistency_{d:+g}", f"consistency cutoff {d:+g}", None, "cutoff outside [0, 1]", {"kind": "consistency", "shift": d}))
    for d in params.frequency_shifts:
        val = ref_cutoffs["frequency_threshold"] + d
        if val >= 1:
            add(f"frequency_{d:+d}", f"frequency cutoff {d:+d}", ref_anchors, cutoffs(frequency_threshold=val), {"kind": "frequency", "shift": d})
        else:
            configs.append(MechanicalConfig(f"frequency_{d:+d}", f"frequency cutoff {d:+d}", None, "cutoff below 1", {"kind": "frequency", "shift": d}))
    return configs
