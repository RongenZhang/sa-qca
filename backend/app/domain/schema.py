"""Builds the JSON Schema for an agent's calibration decision (see docs/protocol-to-code.md)."""

from __future__ import annotations

from typing import Any

ANCHOR_KEYS = ("full_non_membership", "crossover", "full_membership")


def _calibration_def() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["anchors", "rationale"],
        "properties": {
            "anchors": {
                "type": "object",
                "additionalProperties": False,
                "required": list(ANCHOR_KEYS),
                "properties": {k: {"type": "number"} for k in ANCHOR_KEYS},
            },
            "rationale": {
                "type": "object",
                "additionalProperties": False,
                "required": list(ANCHOR_KEYS),
                "properties": {k: {"type": "string", "minLength": 1} for k in ANCHOR_KEYS},
            },
        },
    }


BREAK_KEYS = ("break_0", "break_33", "break_67")
KINDS = ("direct", "breakpoints", "precalibrated")


def _breakpoints_def() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["breakpoints", "rationale"],
        "properties": {
            "breakpoints": {
                "type": "object",
                "additionalProperties": False,
                "required": list(BREAK_KEYS),
                "properties": {k: {"type": "number"} for k in BREAK_KEYS},
            },
            "rationale": {
                "type": "object",
                "additionalProperties": False,
                "required": list(BREAK_KEYS),
                "properties": {k: {"type": "string", "minLength": 1} for k in BREAK_KEYS},
            },
        },
    }


def build_decision_schema(conditions: list[str] | list[tuple[str, str]], outcome_kind: str = "direct") -> dict[str, Any]:
    """`conditions` is a list of names (all calibrated directly) or of (name, kind) pairs. Conditions whose values are
    already calibrated (kind "precalibrated") are fixed and therefore do not appear in the decision at all."""
    pairs = [(c, "direct") if isinstance(c, str) else c for c in conditions]
    asked = [(n, k) for n, k in pairs if k != "precalibrated"]
    ref = {"direct": {"$ref": "#/$defs/calibration"}, "breakpoints": {"$ref": "#/$defs/breakpoints"}}
    if outcome_kind not in ref:
        raise ValueError(f"the outcome must be calibrated by the agent (kind direct or breakpoints), not {outcome_kind!r}")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "CalibrationDecision",
        "type": "object",
        "additionalProperties": False,
        "required": ["conditions", "outcome", "truth_table"],
        "properties": {
            "conditions": {
                "type": "object",
                "additionalProperties": False,
                "required": [n for n, _ in asked],
                "properties": {n: dict(ref[k]) for n, k in asked},
            },
            "outcome": dict(ref[outcome_kind]),
            "truth_table": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "consistency_threshold",
                    "frequency_threshold",
                    "consistency_rationale",
                    "frequency_rationale",
                ],
                "properties": {
                    "consistency_threshold": {"type": "number", "minimum": 0, "maximum": 1},
                    "frequency_threshold": {"type": "integer", "minimum": 1},
                    "pri_threshold": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
                    "consistency_rationale": {"type": "string", "minLength": 1},
                    "frequency_rationale": {"type": "string", "minLength": 1},
                    "pri_rationale": {"type": ["string", "null"]},
                },
            },
        },
        "$defs": {"calibration": _calibration_def(), "breakpoints": _breakpoints_def()},
    }
