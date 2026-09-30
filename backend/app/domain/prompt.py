"""Versioned prompt rendering (protocol step 3). Sends summary statistics only, never raw rows."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib import resources
from typing import Any

from jinja2 import Environment, StrictUndefined

from app.domain.schema import build_decision_schema

DEFAULT_TEMPLATE_VERSION = "default_v1"


@dataclass(frozen=True)
class RoleSpec:
    name: str
    description: str


@dataclass(frozen=True)
class VariableSpec:
    name: str
    role: str  # "condition" | "outcome"
    direction: str
    construct_definition: str
    instrument: str
    units: str
    stats: dict[str, Any]


def load_default_template() -> str:
    return resources.files("app.domain").joinpath("templates/default_v1.j2").read_text()


def prompt_warnings(variables: list[VariableSpec]) -> list[str]:
    """Step 3 guard: an agent given only statistics tends to return a percentile rule."""
    out = []
    for v in variables:
        if not v.construct_definition.strip():
            out.append(f"{v.name}: construct definition is empty")
        if not v.instrument.strip():
            out.append(f"{v.name}: measurement instrument is empty")
    return out


def case_description_warnings(text: str) -> list[str]:
    """A thin description gives agents (and the role-derivation step) little to reason from."""
    n = len(text.strip())
    if n == 0:
        return ["case description is empty: agents will not know who or what the cases are"]
    if n < 400:
        return [f"case description is short ({n} characters): say who or what the cases are, the setting and period, "
                "how the outcome shows up in practice, and what the decision or process involves"]
    return []


def _histogram_text(stats: dict[str, Any]) -> str:
    return "; ".join(f"{b['lower']} to {b['upper']}: {b['count']}" for b in stats["histogram"])


def render_prompt(
    template: str,
    variables: list[VariableSpec],
    case_description: str,
    role: RoleSpec | None = None,
    validation_errors: list[str] | None = None,
) -> str:
    env = Environment(undefined=StrictUndefined, keep_trailing_newline=True, trim_blocks=True, lstrip_blocks=True)
    schema = build_decision_schema([v.name for v in variables if v.role == "condition"])
    ctx_vars = [
        {**v.__dict__, "histogram_text": _histogram_text(v.stats)} for v in variables
    ]
    return env.from_string(template).render(
        role=role,
        case_description=case_description,
        variables=ctx_vars,
        json_schema=json.dumps(schema, indent=2),
        validation_errors=validation_errors or [],
    )


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()
