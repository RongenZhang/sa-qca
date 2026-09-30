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


def build_decision_schema(condition_names: list[str]) -> dict[str, Any]:
    ref = {"$ref": "#/$defs/calibration"}
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
                "required": list(condition_names),
                "properties": {n: dict(ref) for n in condition_names},
            },
            "outcome": dict(ref),
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
        "$defs": {"calibration": _calibration_def()},
    }
