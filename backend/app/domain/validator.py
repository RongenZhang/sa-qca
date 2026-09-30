"""Structural validation (protocol step 5).

The validator NEVER modifies its input: it parses the raw model text strictly and either
accepts it as-is or returns errors. No trimming, clamping, rounding or code-fence stripping.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft202012Validator

from app.domain.schema import ANCHOR_KEYS, build_decision_schema


@dataclass(frozen=True)
class VarInfo:
    name: str
    direction: str  # "positive" | "negative"
    min: float
    max: float


@dataclass(frozen=True)
class ValidationError:
    code: str  # json_parse | schema | ordering | range | blank_rationale | threshold
    path: str
    message: str


@dataclass
class ValidationResult:
    ok: bool
    errors: list[ValidationError] = field(default_factory=list)
    decision: dict[str, Any] | None = None


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-finite number {name} is not valid JSON")


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def validate_decision(
    raw_text: str,
    conditions: list[VarInfo],
    outcome: VarInfo,
    tolerance: float = 0.0,
) -> ValidationResult:
    """`tolerance` is a fraction of the observed range allowed beyond min/max (0 = exactly the range)."""
    try:
        parsed = json.loads(raw_text, parse_constant=_reject_constant)
    except (ValueError, TypeError) as e:
        return ValidationResult(False, [ValidationError("json_parse", "$", str(e))])

    schema = build_decision_schema([c.name for c in conditions])
    schema_errors = sorted(
        Draft202012Validator(schema).iter_errors(parsed), key=lambda e: list(map(str, e.path))
    )
    if schema_errors:
        return ValidationResult(
            False,
            [
                ValidationError("schema", "$." + ".".join(map(str, e.path)) if e.path else "$", e.message)
                for e in schema_errors
            ],
        )

    errors: list[ValidationError] = []
    for var, block in [(c, parsed["conditions"][c.name]) for c in conditions] + [
        (outcome, parsed["outcome"])
    ]:
        base = "$.outcome" if var is outcome else f"$.conditions.{var.name}"
        a = [block["anchors"][k] for k in ANCHOR_KEYS]
        fn, cr, fm = a
        if not all(math.isfinite(x) for x in a):
            errors.append(ValidationError("schema", base, "anchors must be finite numbers"))
            continue
        increasing = fn < cr < fm
        decreasing = fn > cr > fm
        if var.direction == "positive" and not increasing:
            errors.append(ValidationError("ordering", base, "positive orientation requires full_non_membership < crossover < full_membership"))
        elif var.direction == "negative" and not decreasing:
            errors.append(ValidationError("ordering", base, "negative orientation requires full_non_membership > crossover > full_membership"))
        pad = tolerance * (var.max - var.min)
        lo, hi = var.min - pad, var.max + pad
        for k, x in zip(ANCHOR_KEYS, a, strict=True):
            if x < lo or x > hi:
                errors.append(ValidationError("range", f"{base}.anchors.{k}", f"{x} is outside the allowed range [{lo}, {hi}]"))
        for k in ANCHOR_KEYS:
            if not block["rationale"][k].strip():
                errors.append(ValidationError("blank_rationale", f"{base}.rationale.{k}", "rationale is blank"))

    tt = parsed["truth_table"]
    for k in ("consistency_rationale", "frequency_rationale"):
        if not tt[k].strip():
            errors.append(ValidationError("blank_rationale", f"$.truth_table.{k}", "rationale is blank"))
    if tt.get("pri_threshold") is not None and not (tt.get("pri_rationale") or "").strip():
        errors.append(ValidationError("blank_rationale", "$.truth_table.pri_rationale", "pri_threshold given without a rationale"))

    if errors:
        return ValidationResult(False, errors)
    return ValidationResult(True, [], parsed)
