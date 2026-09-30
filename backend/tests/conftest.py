import json
from typing import Any

import pytest

from app.domain.prompt import VariableSpec
from app.domain.stats import describe


def make_vars() -> list[VariableSpec]:
    def v(name: str, role: str, lo: float, hi: float, direction: str = "positive") -> VariableSpec:
        vals = [lo + (hi - lo) * i / 19 for i in range(20)]
        return VariableSpec(name, role, direction, f"{name} construct", f"{name} instrument", "u", describe(vals))

    return [v("A", "condition", 1, 7), v("B", "condition", 0, 100, "negative"), v("Y", "outcome", 0, 100)]


@pytest.fixture
def variables() -> list[VariableSpec]:
    return make_vars()


def good_decision() -> dict[str, Any]:
    r = {k: "because" for k in ("full_non_membership", "crossover", "full_membership")}
    return {
        "conditions": {
            "A": {"anchors": {"full_non_membership": 2, "crossover": 4, "full_membership": 6}, "rationale": dict(r)},
            "B": {"anchors": {"full_non_membership": 80, "crossover": 50, "full_membership": 20}, "rationale": dict(r)},
        },
        "outcome": {"anchors": {"full_non_membership": 25, "crossover": 50, "full_membership": 75}, "rationale": dict(r)},
        "truth_table": {
            "consistency_threshold": 0.8, "frequency_threshold": 1, "pri_threshold": None,
            "consistency_rationale": "c", "frequency_rationale": "f", "pri_rationale": None,
        },
    }


def good_text() -> str:
    return json.dumps(good_decision())
