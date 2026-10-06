"""AI-assisted planning (suggested stakeholders and conditions) with the same discipline as the rest of the tool:
the prompt is visible before it is sent, the answer must match a schema, a failed answer gets exactly one further
attempt with the errors appended, nothing a model returns is edited, and every call is logged. Only the text the
researcher wrote is ever sent: never data rows. Without a model, a clearly labelled scripted fallback is used."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from jinja2 import Environment, StrictUndefined
from jsonschema import Draft202012Validator
from sqlalchemy.orm import Session

from app.db.models import HelperCall
from app.domain.prompt import load_template
from app.domain.validator import ValidationError
from app.llm.base import LLMProvider, ProviderError, RateLimitError

PLANNING = ("stakeholders", "conditions")
KINDS = (*PLANNING, "interpretation")
NAME_PATTERN = r"^[A-Za-z][A-Za-z0-9_]{0,15}$"


class HelperError(Exception):
    """The provider could not answer (not a validation failure)."""


def _str(lo: int, hi: int) -> dict[str, Any]:
    return {"type": "string", "minLength": lo, "maxLength": hi}


SCHEMAS: dict[str, dict[str, Any]] = {
    "stakeholders": {
        "type": "object", "additionalProperties": False, "required": ["stakeholders"],
        "properties": {"stakeholders": {"type": "array", "minItems": 3, "maxItems": 8, "items": {
            "type": "object", "additionalProperties": False, "required": ["name", "description", "relevance"],
            "properties": {"name": _str(2, 80), "description": _str(60, 1500), "relevance": _str(10, 500)}}}}},
    "conditions": {
        "type": "object", "additionalProperties": False, "required": ["conditions"],
        "properties": {"conditions": {"type": "array", "minItems": 3, "maxItems": 8, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["name", "definition", "how_to_measure", "calibration", "direction", "rationale"],
            "properties": {"name": {"type": "string", "pattern": NAME_PATTERN}, "definition": _str(20, 800),
                           "how_to_measure": _str(10, 800), "calibration": {"enum": ["direct", "breakpoints", "precalibrated"]},
                           "direction": {"enum": ["positive", "negative"]}, "rationale": _str(15, 600)}}}}},
}


def _compact_facts(facts: dict[str, Any]) -> str:
    keep: dict[str, Any] = {k: facts[k] for k in ("kind", "reference", "paths", "agreement", "mechanical_matches_analyst_share", "scripted", "reps") if k in facts}
    keep["stakeholder_and_other_sources"] = [{k: s[k] for k in ("label", "kind", "n_valid", "n_invalid", "invalid_rate", "modal_solution", "modal_share",
                                                                 "distinct_solutions", "path_share", "similarity_to_analyst_mean", "calibration", "cutoffs") if k in s} for s in facts["sources"]]
    return json.dumps(keep, indent=1, ensure_ascii=False)


SCHEMAS["interpretation"] = {
    "type": "object", "additionalProperties": False,
    "required": ["headline", "robust_findings", "contested_findings", "stakeholder_perspectives", "implications", "caveats"],
    "properties": {
        "headline": _str(20, 500),
        "robust_findings": {"type": "array", "maxItems": 12, "items": {"type": "object", "additionalProperties": False, "required": ["path", "meaning"],
                                                                         "properties": {"path": _str(1, 200), "meaning": _str(30, 1500)}}},
        "contested_findings": {"type": "array", "maxItems": 16, "items": {
            "type": "object", "additionalProperties": False, "required": ["path", "holds_under", "fails_under", "meaning"],
            "properties": {"path": _str(1, 200), "holds_under": {"type": "array", "items": _str(1, 120)}, "fails_under": {"type": "array", "items": _str(1, 120)},
                           "meaning": _str(30, 1800)}}},
        "stakeholder_perspectives": {"type": "array", "minItems": 1, "maxItems": 12, "items": {
            "type": "object", "additionalProperties": False, "required": ["stakeholder", "reading", "implication"],
            "properties": {"stakeholder": _str(1, 120), "reading": _str(30, 1800), "implication": _str(15, 1500)}}},
        "implications": _str(30, 3000),
        "caveats": {"type": "array", "minItems": 1, "maxItems": 10, "items": _str(10, 700)},
    },
}


def build_prompt(kind: str, inputs: dict[str, Any], validation_errors: list[str] | None = None) -> str:
    env = Environment(undefined=StrictUndefined, keep_trailing_newline=True, trim_blocks=True, lstrip_blocks=True)
    return env.from_string(load_template(f"assist_{kind}_v1")).render(
        phenomenon=inputs["phenomenon"].strip(),
        outcome_name=(inputs.get("outcome") or {}).get("name", ""),
        outcome_description=(inputs.get("outcome") or {}).get("description", ""),
        existing=inputs.get("existing") or [],
        stakeholders=inputs.get("stakeholders") or [],
        conditions=inputs.get("conditions") or [],
        count=int(inputs.get("count") or 5),
        facts_json=_compact_facts(inputs["facts"]) if kind == "interpretation" else "",
        json_schema=json.dumps(SCHEMAS[kind], indent=2),
        validation_errors=validation_errors or [],
    )


def check_inputs(kind: str, inputs: dict[str, Any]) -> None:
    if kind not in KINDS:
        raise ValueError(f"unknown helper {kind!r}")
    if kind == "interpretation":
        if not isinstance(inputs.get("facts"), dict) or "paths" not in inputs["facts"] or "sources" not in inputs["facts"]:
            raise ValueError("the interpretation needs the computed facts of a finished run")
        return
    if len(str(inputs.get("phenomenon", "")).strip()) < 20:
        raise ValueError("describe the phenomenon you want to study first (at least a sentence or two)")
    if len(str(inputs.get("phenomenon", ""))) > 20_000:
        raise ValueError("the phenomenon description is too long")


def validate(kind: str, text: str, inputs: dict[str, Any]) -> tuple[bool, list[ValidationError], dict[str, Any] | None]:
    try:
        parsed = json.loads(text, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
    except (ValueError, TypeError) as e:
        return False, [ValidationError("json_parse", "$", str(e))], None
    errs = [ValidationError("schema", "$." + ".".join(map(str, e.path)) if e.path else "$", e.message)
            for e in sorted(Draft202012Validator(SCHEMAS[kind]).iter_errors(parsed), key=lambda e: list(map(str, e.path)))]
    if errs:
        return False, errs, None
    if kind == "interpretation":
        g = _grounding_errors(parsed, inputs["facts"])
        return (not g), g, (parsed if not g else None)
    items = parsed[kind]
    names = [i["name"].strip().lower() for i in items]
    if len(set(names)) != len(names):
        errs.append(ValidationError("duplicate", f"$.{kind}", "names must be unique"))
    existing = {str(e.get("name", "")).strip().lower() for e in inputs.get("existing") or []}
    out_name = str((inputs.get("outcome") or {}).get("name", "")).strip().lower()
    for n in names:
        if n in existing:
            errs.append(ValidationError("duplicate", f"$.{kind}", f"{n!r} is already chosen"))
        if kind == "conditions" and out_name and n == out_name:
            errs.append(ValidationError("duplicate", f"$.{kind}", f"{n!r} is the outcome, not a condition"))
    return (not errs), errs, (parsed if not errs else None)


def _grounding_errors(parsed: dict[str, Any], facts: dict[str, Any]) -> list[ValidationError]:
    """The narrative may only talk about what the computed facts contain."""
    cls = {p["path"]: p["classification"] for p in facts["paths"]}
    people = {s["label"] for s in facts["sources"] if s["kind"] == "stakeholder"}
    errs: list[ValidationError] = []
    for i, f in enumerate(parsed["robust_findings"]):
        if f["path"] not in cls:
            errs.append(ValidationError("grounding", f"$.robust_findings[{i}].path", f"{f['path']!r} is not a path in the facts"))
        elif cls[f["path"]] != "robust":
            errs.append(ValidationError("grounding", f"$.robust_findings[{i}].path", f"{f['path']!r} is classified {cls[f['path']]!r}, not robust"))
    for i, f in enumerate(parsed["contested_findings"]):
        if f["path"] not in cls:
            errs.append(ValidationError("grounding", f"$.contested_findings[{i}].path", f"{f['path']!r} is not a path in the facts"))
        elif cls[f["path"]] == "robust":
            errs.append(ValidationError("grounding", f"$.contested_findings[{i}].path", f"{f['path']!r} is robust, not contested"))
        for who in (*f["holds_under"], *f["fails_under"]):
            if who not in people:
                errs.append(ValidationError("grounding", f"$.contested_findings[{i}]", f"{who!r} is not a stakeholder in the facts"))
    for i, p in enumerate(parsed["stakeholder_perspectives"]):
        if p["stakeholder"] not in people:
            errs.append(ValidationError("grounding", f"$.stakeholder_perspectives[{i}].stakeholder", f"{p['stakeholder']!r} is not a stakeholder in the facts"))
    return errs


# ---------------------------------------------------------------------------------------------------------------
# Scripted fallback: used when no model is connected (and always on the public demo). Not language-model output.
# ---------------------------------------------------------------------------------------------------------------

def _topic(inputs: dict[str, Any]) -> str:
    name = str((inputs.get("outcome") or {}).get("name", "")).strip()
    return name or str(inputs["phenomenon"]).strip().split(".")[0][:90]


def scripted(kind: str, inputs: dict[str, Any]) -> dict[str, Any]:
    if kind == "interpretation":
        from app.engine.interpret import template_narrative

        return {"interpretation": template_narrative(inputs["facts"]), "generic": False,
                "notice": "Written by fixed rules from the computed facts, not by a language model."}
    """Returns {"items": [...], "generic": bool, "notice": str}. For the bundled demo study the suggestions are the demo's own;
    for anything else they are generic prompts to think with, never tailored to the researcher's topic."""
    if inputs.get("demo"):
        from app.demo import demo_study

        d = demo_study()
        items = [{k: v for k, v in s.items() if k != "ai"} for s in d["stakeholders"]] if kind == "stakeholders" else [
            {"name": c["name"], "definition": c["definition"], "how_to_measure": c["how_to_measure"], "calibration": c["calibration"],
             "direction": c["direction"], "rationale": "Part of the demo study."} for c in d["conditions"]]
        return {"items": items, "generic": False, "notice": "Scripted suggestions for the bundled demo study, not language-model output."}
    if kind == "stakeholders":
        t = _topic(inputs)
        items = [
            {"name": "People who do the work", "relevance": "They see how things really run and what the measures miss.",
             "description": f"Those directly involved in carrying out or living with {t}. They see the day-to-day reality, have first-hand evidence, and tend to judge a measure by whether it matches what they experience in practice, which can make them more or less demanding than outsiders about what counts as high."},
            {"name": "People who decide or fund", "relevance": "They set priorities and judge success by results and risk.",
             "description": f"Those who authorise, resource or answer for {t}. They see aggregate results and costs rather than individual cases, care about accountability and risk, and may set a different bar for what counts as enough than the people doing the work."},
            {"name": "People affected by the outcome", "relevance": "They experience the consequences, so their standard of 'good enough' differs.",
             "description": f"Those who experience the consequences of {t} without controlling it. They judge outcomes by their own benefit or harm, may notice effects that internal measures do not capture, and can reasonably consider a result high or low on grounds the others do not use."},
            {"name": "Independent evaluators", "relevance": "They apply an external, usually more demanding, standard.",
             "description": f"Outside analysts or reviewers who assess {t} with limited insider context. They rely on documented evidence, discount self-reports, and often apply a more demanding standard for what counts as clearly present."},
        ]
        return {"items": items, "generic": True, "notice": "Generic prompts to think with, not tailored to your topic. Connect a model in AI settings for suggestions drawn from your own description, or write your own groups."}
    return {"items": [], "generic": True, "notice": "Scripted mode cannot suggest conditions for your topic. Enter your conditions yourself, or connect a model in AI settings to get suggestions drawn from your description."}


# ---------------------------------------------------------------------------------------------------------------
# Calling a model
# ---------------------------------------------------------------------------------------------------------------

def _log(session: Session, **kw: Any) -> HelperCall:
    row = HelperCall(**kw)
    session.add(row)
    session.flush()
    return row


def _complete(provider: LLMProvider, prompt: str, model: str, sampling: dict[str, Any], sleep: Callable[[float], None]) -> Any:
    for n in range(4):
        try:
            return provider.complete(prompt, model=model, sampling=sampling)
        except RateLimitError as e:
            if n == 3:
                raise HelperError("the model provider is rate-limiting requests; please try again shortly") from e
            sleep(e.retry_after if e.retry_after is not None else 2.0 * 2**n)
        except ProviderError as e:
            raise HelperError(str(e)) from e
    raise HelperError("unreachable")


def run_helper(session: Session, kind: str, inputs: dict[str, Any], provider: LLMProvider | None, model: str,
               sampling: dict[str, Any], project_id: str | None = None, sleep: Callable[[float], None] = time.sleep,
               run_config_id: int | None = None) -> dict[str, Any]:
    """Runs one helper. `provider=None` means scripted. Returns the suggestions plus what is needed to label and trace them."""
    check_inputs(kind, inputs)
    if provider is None:
        out = scripted(kind, inputs)
        row = _log(session, project_id=project_id, run_config_id=run_config_id, kind=kind, provider="scripted", prompt="(scripted: no model was called)",
                   raw_response=json.dumps(out), parsed=out, validation_ok=True)
        session.commit()
        return {"items": [], **out, "provider": "scripted", "model_id": None, "ai_generated": False, "helper_call_ids": [row.id]}
    errors: list[str] | None = None
    ids: list[int] = []
    for attempt in ("first", "validation_retry"):
        prompt = build_prompt(kind, inputs, errors)
        resp = _complete(provider, prompt, model, sampling, sleep)
        ok, errs, parsed = validate(kind, resp.text, inputs)
        row = _log(session, project_id=project_id, run_config_id=run_config_id, kind=kind, provider=provider.name, model_id=resp.model_id, sampling=sampling,
                   attempt_kind=attempt, prompt=prompt, raw_response=resp.text, parsed=parsed, validation_ok=ok,
                   validation_errors=[e.__dict__ for e in errs], tokens_in=resp.tokens_in, tokens_out=resp.tokens_out)
        ids.append(row.id)
        if ok and parsed is not None:
            session.commit()
            body: dict[str, Any] = {"interpretation": parsed, "items": []} if kind == "interpretation" else {"items": parsed[kind]}
            return {**body, "generic": False, "notice": "", "provider": provider.name, "model_id": resp.model_id,
                    "ai_generated": True, "helper_call_ids": ids}
        errors = [f"[{e.code}] {e.path}: {e.message}" for e in errs]
    session.commit()
    raise HelperError("the model's answer did not match the required format twice, so nothing was added. Details: " + "; ".join(errors or []))
