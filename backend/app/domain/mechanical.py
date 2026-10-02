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

from app.domain.schema import ANCHOR_KEYS, BREAK_KEYS
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
    source: str = "mechanical"  # mechanical | analyst


def _shift_anchor(sorted_vals: list[float], x: float, shift: float) -> float:
    rank = percentile_rank(sorted_vals, x) + shift
    rank = min(100.0, max(0.0, rank))  # rank bound on the percentile scale, not on raw anchors
    return quantile(sorted_vals, rank / 100.0)


def _ordered(a: dict[str, float], direction: str) -> bool:
    fn, cr, fm = list(a.values())  # the three values in order: anchors or breakpoints
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


@dataclass(frozen=True)
class SkaaningParams:
    """Skaaning (2011) style: each condition gets a lower / original / higher anchor set (all three
    anchors moved together by a fixed raw offset), crossed factorially across conditions. The outcome is
    not perturbed by default. Frequency cutoff raised, consistency moved up and down. `shift_fraction`
    is a share of the observed range (Skaaning used hand-picked raw offsets, roughly 5-15% of range)."""

    shift_fraction: float = 0.05
    perturb_outcome: bool = False
    consistency_shifts: tuple[float, ...] = (-0.1, 0.1)
    frequency_shifts: tuple[int, ...] = (1,)
    max_conditions: int = 6  # 3**k - 1 analyses; refuse silently-huge grids


def generate_skaaning_configs(
    data: dict[str, list[float]],
    reference: dict[str, dict[str, float]],
    directions: dict[str, str],
    outcome: str,
    ref_cutoffs: dict[str, Any],
    params: SkaaningParams = SkaaningParams(),
    kinds: dict[str, str] | None = None,
) -> list[MechanicalConfig]:
    import itertools

    kinds = kinds or {}

    def keys(n: str) -> tuple[str, ...]:
        return BREAK_KEYS if kinds.get(n) == "breakpoints" else ANCHOR_KEYS

    names = [n for n in reference if n != outcome]
    if len(names) > params.max_conditions:
        raise ValueError(f"{len(names)} conditions gives 3**{len(names)} - 1 configurations; raise max_conditions")
    # Offsets are a share of the observed range for anchors. Breakpoints on skewed counts would be swamped by a range-based
    # offset, so for them the offset is a share of the distance between the reference's first and last breakpoint.
    span = {n: (abs(reference[n][BREAK_KEYS[2]] - reference[n][BREAK_KEYS[0]]) if kinds.get(n) == "breakpoints"
                else max(data[n]) - min(data[n])) for n in [*names, outcome]}

    def moved(n: str, level: int) -> dict[str, float]:
        off = level * params.shift_fraction * span[n]
        return {k: reference[n][k] + off for k in keys(n)}

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

    def decision(anchor_map: dict[str, dict[str, float]], tt: dict[str, Any], note: str) -> dict[str, Any]:
        def block(n: str) -> dict[str, Any]:
            field = "breakpoints" if kinds.get(n) == "breakpoints" else "anchors"
            return {field: anchor_map[n], "rationale": {k: f"mechanical: {note}" for k in keys(n)}}

        return {"conditions": {n: block(n) for n in names}, "outcome": block(outcome), "truth_table": cutoffs_(tt)}

    def cutoffs_(tt: dict[str, Any]) -> dict[str, Any]:
        return tt

    out_levels = (-1, 0, 1) if params.perturb_outcome else (0,)
    configs: list[MechanicalConfig] = []
    for combo in itertools.product((-1, 0, 1), repeat=len(names)):
        for ol in out_levels:
            if all(c == 0 for c in combo) and ol == 0:
                continue
            amap = {n: moved(n, lv) for n, lv in zip(names, combo, strict=True)}
            amap[outcome] = moved(outcome, ol)
            label = ",".join(f"{n}{lv:+d}" for n, lv in zip(names, combo, strict=True)) + (f",{outcome}{ol:+d}" if params.perturb_outcome else "")
            bad = [n for n, a in amap.items() if not _ordered(a, directions[n])]
            cid = f"skaaning_{label}"
            pert = {"kind": "skaaning_factorial", "levels": dict(zip(names, combo, strict=True)), "outcome_level": ol}
            if bad:
                configs.append(MechanicalConfig(cid, label, None, f"ordering broken for: {', '.join(bad)}", pert))
            else:
                configs.append(MechanicalConfig(cid, label, decision(amap, cutoffs(), label), None, pert))
    ref_map = {n: dict(reference[n]) for n in [*names, outcome]}
    for d in params.consistency_shifts:
        v = round(ref_cutoffs["consistency_threshold"] + d, 10)
        pert = {"kind": "consistency", "shift": d}
        if 0.0 <= v <= 1.0:
            configs.append(MechanicalConfig(f"consistency_{d:+g}", f"consistency {d:+g}", decision(ref_map, cutoffs(consistency_threshold=v), f"consistency {d:+g}"), None, pert))
        else:
            configs.append(MechanicalConfig(f"consistency_{d:+g}", f"consistency {d:+g}", None, "cutoff outside [0, 1]", pert))
    for d in params.frequency_shifts:
        v = ref_cutoffs["frequency_threshold"] + d
        pert = {"kind": "frequency", "shift": d}
        if v >= 1:
            configs.append(MechanicalConfig(f"frequency_{d:+d}", f"frequency {d:+d}", decision(ref_map, cutoffs(frequency_threshold=v), f"frequency {d:+d}"), None, pert))
        else:
            configs.append(MechanicalConfig(f"frequency_{d:+d}", f"frequency {d:+d}", None, "cutoff below 1", pert))
    return configs
