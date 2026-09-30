"""Bundled demo project (synthetic data) and a deterministic scripted 'LLM' so the tool works with no API key."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

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
                     v.get("units", ""), describe(data[v["name"]]))
        for v in proj["variables"]
    ]
    return {
        "project": proj,
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
        text = json.dumps(self._decision(bias + jitter, break_order=bad), indent=2)
        return LLMResponse(text=text, model_id="demo-mock-1", tokens_in=len(prompt) // 4, tokens_out=len(text) // 4)

    def _decision(self, shift: float, break_order: bool) -> dict[str, Any]:
        d = self.demo
        stats = {v.name: v.stats for v in d["variables"]}
        first_cond = next(v.name for v in d["variables"] if v.role == "condition")

        def block(n: str) -> dict[str, Any]:
            span = stats[n]["max"] - stats[n]["min"]
            if n in d["reference"]:
                base = d["reference"][n]
            else:  # no analyst anchors: quartiles, purely so the test provider can answer
                lo, mid, hi = stats[n]["q1"], stats[n]["median"], stats[n]["q3"]
                neg = d["directions"][n] == "negative"
                base = {"full_non_membership": hi if neg else lo, "crossover": mid, "full_membership": lo if neg else hi}
            a = {k: min(stats[n]["max"], max(stats[n]["min"], base[k] + shift * span)) for k in ANCHOR_KEYS}
            if break_order and n == first_cond:
                a["full_membership"], a["full_non_membership"] = a["full_non_membership"], a["full_membership"]
            why = {
                "full_non_membership": "Below this the cases are clearly outside the set given how the construct is measured.",
                "crossover": "This is where a reasonable observer in my position could not say in or out.",
                "full_membership": "At or above this the construct is unambiguously present.",
            }
            return {"anchors": {k: round(a[k], 4) for k in ANCHOR_KEYS}, "rationale": why}

        tt = dict(d["reference_cutoffs"]) or {"consistency_threshold": 0.8, "frequency_threshold": 1, "pri_threshold": None}
        return {
            "conditions": {v.name: block(v.name) for v in d["variables"] if v.role == "condition"},
            "outcome": block(d["outcome"]),
            "truth_table": {
                "consistency_threshold": tt["consistency_threshold"], "frequency_threshold": tt["frequency_threshold"],
                "pri_threshold": tt.get("pri_threshold"),
                "consistency_rationale": "Keeps only rows that are clearly consistent with sufficiency.",
                "frequency_rationale": "With this many cases a single case can carry a row.",
                "pri_rationale": "Guards against rows that are simultaneously sufficient for the outcome and its negation.",
            },
        }
