"""Bundled demo project (synthetic data) and a deterministic scripted 'LLM' so the tool works with no API key."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.demo_rationales import (
    anchor_rationale,
    breakpoint_rationale,
    consistency_rationale,
    frequency_rationale,
    pri_rationale,
)
from app.domain.prompt import VariableSpec
from app.domain.stats import describe
from app.llm.base import LLMProvider, LLMResponse

DEMO_DIR = Path(__file__).resolve().parents[2] / "demo"
ANCHOR_KEYS = ("full_non_membership", "crossover", "full_membership")

SUGGESTED_ROLES = [
    {"name": "Small-firm owner-manager", "description": "Runs the firm day to day and lives with the consequences of adoption; judges trust and support by what it means for their own time and money.", "relevance": "Closest to the cases."},
    {"name": "Vendor account manager", "description": "Sells and supports the system; sees adoption across many firms and tends to read moderate trust as already sufficient.", "relevance": "Sees cross-firm variation."},
    {"name": "Independent IT consultant", "description": "Advises firms on implementation; holds demanding standards for what counts as real, embedded use.", "relevance": "External evaluator of adoption."},
]


def load_demo() -> dict[str, Any]:
    proj = json.loads((DEMO_DIR / "project.json").read_text())
    rows = list(csv.DictReader((DEMO_DIR / "dataset.csv").open()))
    data = {k: [float(r[k]) for r in rows] for k in rows[0] if k != "case"}
    variables = [
        VariableSpec(v["name"], v["role"], v["direction"], v["construct_definition"], v["instrument"],
                     v.get("units", ""), describe(data[v["name"]]), v.get("calibration", "direct"))
        for v in proj["variables"]
    ]
    return {
        "project": proj,
        "kinds": {v.name: v.calibration for v in variables},
        "condition_order": [v.name for v in variables if v.role == "condition"],
        "data": data,
        "variables": variables,
        "outcome": next(v.name for v in variables if v.role == "outcome"),
        "directions": {v["name"]: v["direction"] for v in proj["variables"]},
        "dir_exp": {v["name"]: v.get("dir_exp") for v in proj["variables"]},
        "reference": {k: v for k, v in proj["reference_spec"].items() if k != "truth_table"},
        "reference_cutoffs": proj["reference_spec"]["truth_table"],
    }


class DemoProvider(LLMProvider):
    """Pre-scripted stand-in for an LLM. Deterministic given (role, call count). Returns mostly valid
    decisions, sometimes an invalid first answer (to exercise the retry) and rarely two invalid answers."""

    name = "demo-mock"
    ROLE_BIAS = {"Small-firm owner-manager": -0.06, "Vendor account manager": -0.10, "Independent IT consultant": 0.10}

    def __init__(self, project: dict[str, Any] | None = None) -> None:
        self.demo = project or load_demo()
        self.counts: dict[str, int] = {}

    def complete(self, prompt: str, *, model: str, sampling: dict[str, Any]) -> LLMResponse:
        m = re.search(r"You are answering as: (.+)", prompt)
        role = m.group(1).strip() if m else "generic"
        md = re.search(r"You are answering as: .+\n(.+?)\n(?:Calibrate|Set the calibration)", prompt, re.S)
        role_desc = md.group(1).strip() if md else ""
        retry = "previous answer was rejected" in prompt
        if not retry:
            self.counts[role] = self.counts.get(role, 0) + 1
        n = self.counts.get(role, 1)
        h = int(hashlib.sha256(f"{role}|{n}".encode()).hexdigest(), 16)
        bias = self.ROLE_BIAS.get(role)
        if bias is None:  # any other role name: a fixed pseudo-random lean derived from the name
            bias = (int(hashlib.sha256(role.encode()).hexdigest(), 16) % 200 - 100) / 1000
        jitter = ((h % 1000) / 1000 - 0.5) * 0.06
        bad = (not retry and h % 6 == 0) or (retry and h % 20 == 0)
        text = json.dumps(self._decision(bias + jitter, bad, role, role_desc), indent=2, ensure_ascii=False)
        return LLMResponse(text=text, model_id="demo-mock-1", tokens_in=len(prompt) // 4, tokens_out=len(text) // 4)

    def _decision(self, shift: float, break_order: bool, role: str = "generic", role_desc: str = "") -> dict[str, Any]:
        d = self.demo
        stats = {v.name: v.stats for v in d["variables"]}
        asked = [v for v in d["variables"] if v.role == "condition" and v.calibration != "precalibrated"]
        first_cond = asked[0].name if asked else d["outcome"]

        def block(n: str) -> dict[str, Any]:
            var = next(v for v in d["variables"] if v.name == n)
            span = stats[n]["max"] - stats[n]["min"]
            neg = d["directions"][n] == "negative"
            if var.calibration == "breakpoints":
                keys = ("break_0", "break_33", "break_67")
                if n in d["reference"]:
                    base = d["reference"][n]
                    spread = abs(base[keys[2]] - base[keys[0]]) or span
                else:  # no analyst breakpoints: boundaries from the quartiles, purely so the test provider can answer
                    q1, med, q3 = stats[n]["q1"], stats[n]["median"], stats[n]["q3"]
                    base = dict(zip(keys, (stats[n]["max"], med, q1) if neg else (stats[n]["min"], med, q3), strict=True))
                    spread = span
                lo_, hi_ = stats[n]["min"], stats[n]["max"]
                b = {k: base[k] + shift * spread for k in keys}
                b[keys[1]] = min(hi_, max(lo_, b[keys[1]]))
                b[keys[2]] = min(hi_, max(lo_, b[keys[2]]))
                ordered = b[keys[0]] > b[keys[1]] > b[keys[2]] if neg else b[keys[0]] < b[keys[1]] < b[keys[2]]
                if not ordered:  # clamping collapsed the boundaries: fall back to the reference/quartile values
                    b = {k: base[k] for k in keys}
                if break_order and n == first_cond:
                    b[keys[0]], b[keys[2]] = b[keys[2]], b[keys[0]]
                vals = {k: round(b[k], 4) for k in keys}
                why = {k: breakpoint_rationale(role, role_desc, var, k, vals[k], d["data"][n]) for k in keys}
                return {"breakpoints": vals, "rationale": why}
            if n in d["reference"]:
                base = d["reference"][n]
            else:  # no analyst anchors: quartiles, purely so the test provider can answer
                lo, mid, hi = stats[n]["q1"], stats[n]["median"], stats[n]["q3"]
                base = {"full_non_membership": hi if neg else lo, "crossover": mid, "full_membership": lo if neg else hi}
            a = {k: min(stats[n]["max"], max(stats[n]["min"], base[k] + shift * span)) for k in ANCHOR_KEYS}
            if break_order and n == first_cond:
                a["full_membership"], a["full_non_membership"] = a["full_non_membership"], a["full_membership"]
            why = {k: anchor_rationale(role, role_desc, var, k, round(a[k], 4), d["data"][n]) for k in ANCHOR_KEYS}
            return {"anchors": {k: round(a[k], 4) for k in ANCHOR_KEYS}, "rationale": why}

        tt = dict(d["reference_cutoffs"]) or {"consistency_threshold": 0.8, "frequency_threshold": 1, "pri_threshold": None}
        n_cases = len(d["data"][d["outcome"]])
        k = sum(1 for v in d["variables"] if v.role == "condition")
        return {
            "conditions": {v.name: block(v.name) for v in asked},
            "outcome": block(d["outcome"]),
            "truth_table": {
                "consistency_threshold": tt["consistency_threshold"], "frequency_threshold": tt["frequency_threshold"],
                "pri_threshold": tt.get("pri_threshold"),
                "consistency_rationale": consistency_rationale(role, tt["consistency_threshold"], n_cases, k),
                "frequency_rationale": frequency_rationale(role, tt["frequency_threshold"], n_cases, k),
                "pri_rationale": pri_rationale(tt["pri_threshold"]) if tt.get("pri_threshold") is not None else None,
            },
        }
