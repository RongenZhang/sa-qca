"""Multi-stakeholder interpretation of the solutions.

Two layers. `build_facts` is deterministic: it reads the stored runs and computes which solution paths hold under every
stakeholder's reading, which depend on whose reading is used, how each stakeholder's calibration differs from the
analyst's, and how stable each reading is. `template_narrative` turns those facts into prose by fixed rules. A model may
also be asked to draft the narrative (see assist.py), but only from these facts, and its answer is checked against them."""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.domain.similarity import jaccard_terms
from app.domain.solution import Term, format_term, solution_key, solution_terms

VALID = {"valid", "valid_no_solution"}
SIMILAR_PCT = 2.0  # a mean calibration shift smaller than this share of the scale is called "similar"
PRESENT_SHARE = 0.5  # a path is "present" in a reading when at least half of that reading's valid runs contain it


def _source_kind(arm: str) -> str:
    return "stakeholder" if arm.startswith("role:") else arm


def _label(arm: str) -> str:
    return arm[5:] if arm.startswith("role:") else {"generic": "Generic reading", "mechanical": "Mechanical perturbation"}.get(arm, arm)


def _modal(counter: Counter[str]) -> tuple[str, int]:
    """Most common solution; ties go to the alphabetically first, so the choice never depends on run order."""
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0]


def _basis(var: dict[str, Any], ref: dict[str, float]) -> float:
    if var.get("calibration") == "breakpoints":
        vals = list(ref.values())
        return abs(vals[-1] - vals[0]) or 1.0
    return (var["stats"]["max"] - var["stats"]["min"]) or 1.0


def _stance(var: dict[str, Any], shift_pct: float) -> str:
    if abs(shift_pct) < SIMILAR_PCT:
        return "similar"
    strict = shift_pct > 0 if var["direction"] == "positive" else shift_pct < 0
    return "stricter" if strict else "more lenient"


def _calibration_profile(runs: list[dict[str, Any]], proj: dict[str, Any]) -> list[dict[str, Any]]:
    """How this source's proposed anchors or breakpoints differ from the analyst's, per variable."""
    out: list[dict[str, Any]] = []
    for var in proj["variables"]:
        ref = proj.get("reference", {}).get(var["name"])
        if var.get("calibration") == "precalibrated" or not ref:
            continue
        key = "outcome" if var["role"] == "outcome" else var["name"]
        shifts = []
        for r in runs:
            a = (r.get("anchors") or {}).get(key)
            if a:
                basis = _basis(var, ref)
                shifts.append(sum((a[k] - ref[k]) / basis for k in ref) / len(ref))
        if not shifts:
            continue
        pct = round(100 * sum(shifts) / len(shifts), 1)
        out.append({"variable": var["name"], "calibration": var.get("calibration", "direct"), "shift_pct_of_scale": pct,
                    "stance": _stance(var, pct), "n_runs": len(shifts)})
    return out


def build_facts(results: dict[str, Any], kind: str = "parsimonious", policy: str = "union") -> dict[str, Any]:
    runs = results["runs"]
    proj = results["project"]
    ref_run = next((r for r in runs if r["arm"] == "reference"), None)
    ref_terms = solution_terms(ref_run["solutions"][kind], policy) if ref_run and ref_run.get("solutions") else None
    ref_paths = sorted(format_term(t) for t in ref_terms) if ref_terms is not None else []
    ref_key = solution_key(ref_terms) if ref_terms is not None else None

    arms = [a for a in dict.fromkeys(r["arm"] for r in runs) if a != "reference"]
    sources: list[dict[str, Any]] = []
    by_source_terms: dict[str, list[frozenset[Term]]] = {}
    for arm in arms:
        rs = [r for r in runs if r["arm"] == arm]
        valid = [r for r in rs if r["status"] in VALID and r.get("solutions") is not None]
        term_sets = [solution_terms(r["solutions"][kind], policy) for r in valid]
        by_source_terms[arm] = term_sets
        keys = Counter(solution_key(t) for t in term_sets)
        modal, modal_n = _modal(keys) if keys else (None, 0)
        path_count: Counter[str] = Counter(format_term(t) for ts in term_sets for t in ts)
        agents = [r for r in rs if r["status"] != "provider_error"]
        sim = [jaccard_terms(t, ref_terms) for t in term_sets] if ref_terms is not None else []
        cut = [r["cutoffs"] for r in valid if r.get("cutoffs")]
        sources.append({
            "id": arm, "label": _label(arm), "kind": _source_kind(arm),
            "n_runs": len(agents), "n_valid": len(valid), "n_invalid": sum(1 for r in agents if r["status"] == "invalid"),
            "invalid_rate": (sum(1 for r in agents if r["status"] == "invalid") / len(agents)) if agents and arm not in ("mechanical",) else None,
            "modal_solution": modal, "modal_share": (modal_n / len(valid)) if valid else None, "distinct_solutions": len(keys),
            "solutions": [{"solution": k, "runs": n} for k, n in sorted(keys.items(), key=lambda kv: (-kv[1], kv[0]))],
            "path_share": {p: c / len(valid) for p, c in sorted(path_count.items())} if valid else {},
            "similarity_to_analyst_mean": (sum(sim) / len(sim)) if sim else None,
            "matches_analyst_share": (sum(1 for t in term_sets if solution_key(t) == ref_key) / len(term_sets)) if ref_key and term_sets else None,
            "calibration": _calibration_profile(valid, proj) if arm != "mechanical" else [],
            "cutoffs": {"consistency_mean": round(sum(c["consistency_threshold"] for c in cut) / len(cut), 3),
                        "frequency_mean": round(sum(c["frequency_threshold"] for c in cut) / len(cut), 2)} if cut and arm != "mechanical" else None,
        })

    stake = [s for s in sources if s["kind"] == "stakeholder" and s["n_valid"] > 0]
    others = {s["id"]: s for s in sources if s["kind"] != "stakeholder"}
    all_paths = sorted(set(ref_paths) | {p for s in sources for p in s["path_share"]})
    paths: list[dict[str, Any]] = []
    for p in all_paths:
        has = [s["label"] for s in stake if s["path_share"].get(p, 0) >= PRESENT_SHARE]
        lacks = [s["label"] for s in stake if s["path_share"].get(p, 0) < PRESENT_SHARE]
        in_ref = p in ref_paths
        if not stake:
            cls = "not evaluated"
        elif not lacks:
            cls = "robust"
        elif not has:
            cls = "analyst-only" if in_ref else "rare"
        elif len(has) == 1 and len(stake) > 2:
            cls = "stakeholder-specific"
        else:
            cls = "contested"
        contrast = []
        if has and lacks:  # descriptive: where do those who lack this path differ in calibration from those who have it?
            for v in {c["variable"] for s in stake for c in s["calibration"]}:
                def mean_shift(group: list[str], v: str = v) -> float | None:
                    xs = [c["shift_pct_of_scale"] for s in stake if s["label"] in group for c in s["calibration"] if c["variable"] == v]
                    return sum(xs) / len(xs) if xs else None
                a, b = mean_shift(lacks), mean_shift(has)
                if a is not None and b is not None:
                    contrast.append({"variable": v, "shift_where_absent": round(a, 1), "shift_where_present": round(b, 1), "gap": round(a - b, 1)})
            contrast.sort(key=lambda c: -abs(c["gap"]))
        paths.append({"path": p, "in_analyst_solution": in_ref, "classification": cls, "present_under": has, "absent_under": lacks,
                      "share_by_source": {s["label"]: round(s["path_share"].get(p, 0), 2) for s in sources}, "calibration_contrast": contrast[:3]})

    modal_keys = {s["label"]: s["modal_solution"] for s in stake}
    pairs = [(a, b) for i, a in enumerate(stake) for b in stake[i + 1:]]
    between_same = (sum(1 for a, b in pairs if a["modal_solution"] == b["modal_solution"]) / len(pairs)) if pairs else None
    modal_terms = {s["label"]: next(t for t in by_source_terms[s["id"]] if solution_key(t) == s["modal_solution"]) for s in stake}
    between_sim = (sum(jaccard_terms(modal_terms[a["label"]], modal_terms[b["label"]]) for a, b in pairs) / len(pairs)) if pairs else None
    mech = others.get("mechanical")
    return {
        "kind": kind, "model_policy": policy, "project_name": proj.get("name", ""),
        "reference": {"solution": ref_key, "paths": ref_paths} if ref_key is not None else None,
        "sources": sources, "paths": paths,
        "agreement": {"n_stakeholders": len(stake),
                      "within_reading_mean_modal_share": (sum(s["modal_share"] for s in stake if s["modal_share"] is not None) / len(stake)) if stake else None,
                      "between_readings_same_solution_share": between_same, "between_readings_mean_similarity": between_sim,
                      "modal_solutions": modal_keys},
        "mechanical_matches_analyst_share": mech["matches_analyst_share"] if mech else None,
        "stakeholders_match_analyst": [s["label"] for s in stake if ref_key is not None and s["modal_solution"] == ref_key],
        "provider": results["config"].get("provider"), "model": results["config"].get("model"),
        "scripted": results["config"].get("provider") == "demo-mock", "reps": results["config"].get("reps"),
    }


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{round(100 * x)}%"


def _stance_sentence(profile: list[dict[str, Any]]) -> str:
    groups: dict[str, list[str]] = {"stricter": [], "more lenient": []}
    for c in profile:
        if c["stance"] in groups:
            groups[c["stance"]].append(f"{c['variable']} ({c['shift_pct_of_scale']:+g}% of the scale)")
    parts = []
    if groups["stricter"]:
        parts.append("a stricter bar than the analyst on " + ", ".join(groups["stricter"]))
    if groups["more lenient"]:
        parts.append("a more lenient bar on " + ", ".join(groups["more lenient"]))
    return "set " + " and ".join(parts) if parts else "set calibrations close to the analyst's"


def template_narrative(facts: dict[str, Any]) -> dict[str, Any]:
    """The facts in words, by fixed rules. Same shape as the model-drafted narrative so both render the same way."""
    stake = [s for s in facts["sources"] if s["kind"] == "stakeholder" and s["n_valid"] > 0]
    n = len(stake)
    paths = facts["paths"]
    robust = [p for p in paths if p["classification"] == "robust" and p["in_analyst_solution"]] or [p for p in paths if p["classification"] == "robust"]
    contested = [p for p in paths if p["classification"] in ("contested", "stakeholder-specific", "analyst-only") and p["in_analyst_solution"]]
    alternative = [p for p in paths if not p["in_analyst_solution"] and p["classification"] in ("contested", "stakeholder-specific")]
    ref = facts["reference"]
    kind = facts["kind"]
    if n == 0:
        headline = "No stakeholder reading produced a valid solution, so there is nothing yet to interpret."
    elif ref:
        total = len(ref["paths"])
        held = len([p for p in robust if p["in_analyst_solution"]])
        headline = (f"Of the {total} path{'s' if total != 1 else ''} in the analyst's {kind} solution, {held} hold{'s' if held == 1 else ''} under all {n} stakeholder readings"
                    f" and {len(contested)} depend{'s' if len(contested) == 1 else ''} on whose reading is used.")
    else:
        headline = f"Across {n} stakeholder readings, {len(robust)} path{'s' if len(robust) != 1 else ''} appear under every reading and {len(paths) - len(robust)} under only some."
    robust_f = [{"path": p["path"], "meaning": f"{p['path']} appears in the solution under every stakeholder reading ({', '.join(f'{k}: {_pct(v)}' for k, v in p['share_by_source'].items() if k in [s['label'] for s in stake])} of valid runs), "
                 f"so this finding does not depend on which stakeholder's calibration is used."} for p in robust]
    contested_f = []
    for p in contested + alternative:
        contrast = p["calibration_contrast"]
        why = ""
        if contrast:
            c = contrast[0]
            why = (f" The readings that lose it set {c['variable']} {c['shift_where_absent']:+g}% of the scale away from the analyst on average, against {c['shift_where_present']:+g}% for the readings that keep it; "
                   f"this is descriptive and, with {n} readings, cannot show that the calibration difference caused the change.")
        origin = "an alternative route not in the analyst's solution" if not p["in_analyst_solution"] else "a path in the analyst's solution"
        contested_f.append({"path": p["path"], "holds_under": p["present_under"], "fails_under": p["absent_under"],
                            "meaning": f"{p['path']} is {origin} and is {'present' if p['present_under'] else 'absent'} under {len(p['present_under'])} of {n} readings.{why}"})
    perspectives = []
    for s in stake:
        gaps = [p for p in paths if p["in_analyst_solution"] and p["path"] not in s["path_share"]]
        extra = [p for p in paths if not p["in_analyst_solution"] and s["path_share"].get(p["path"], 0) >= PRESENT_SHARE]
        stable = "stable across its repetitions" if (s["modal_share"] or 0) >= 0.8 else f"variable across its repetitions (its most common solution appears in {_pct(s['modal_share'])} of runs)"
        impl = ("Agrees with the analyst's solution." if s["modal_solution"] == (facts["reference"] or {}).get("solution") else
                ("Does not support " + ", ".join(p["path"] for p in gaps) + "." if gaps else "") + (" Adds " + ", ".join(p["path"] for p in extra) + "." if extra else ""))
        perspectives.append({"stakeholder": s["label"], "reading": f"Typical solution: {s['modal_solution'] or 'none'}. It {_stance_sentence(s['calibration'])}; the reading is {stable}. Invalid answers: {_pct(s['invalid_rate'])}.",
                             "implication": impl.strip() or "No difference from the analyst's solution."})
    mech = facts["mechanical_matches_analyst_share"]
    stake_match = len(facts["stakeholders_match_analyst"])
    implications = []
    if robust:
        implications.append("Findings in the robust group can be reported as insensitive to the stakeholder readings tested.")
    if contested_f:
        implications.append("Contested findings should be reported together with the readings under which they hold and fail, rather than as general results.")
    if mech is not None and n:
        implications.append(f"The mechanical perturbation reproduced the analyst's solution in {_pct(mech)} of its runs, while {stake_match} of {n} stakeholder readings did; "
                            + ("stakeholder readings moved the solution more than the mechanical perturbation did." if stake_match / n < mech else "stakeholder readings were no more disruptive than the mechanical perturbation."))
    caveats = [f"Each stakeholder reading rests on {facts.get('reps') or 'a few'} repetition(s); small numbers of runs make shares coarse."]
    if facts["scripted"]:
        caveats.insert(0, "The calibrations came from a scripted stand-in, not a language model, so this describes how the tool behaves and says nothing about real stakeholders.")
    else:
        caveats.insert(0, "Each stakeholder reading is one structured reading proposed by a language model, not evidence about what real stakeholders think; check it against people who know the setting.")
    low = [s["label"] for s in stake if (s["modal_share"] or 1) < 0.8]
    if low:
        caveats.append("Readings that disagree with themselves across repetitions (" + ", ".join(low) + ") add run-to-run noise to the comparison.")
    inv = [s["label"] for s in stake if (s["invalid_rate"] or 0) > 0.2]
    if inv:
        caveats.append("High invalid-answer rates for " + ", ".join(inv) + " mean part of that reading is missing.")
    return {"headline": headline, "robust_findings": robust_f, "contested_findings": contested_f, "stakeholder_perspectives": perspectives,
            "implications": " ".join(implications) or "There are not yet enough valid readings to draw implications.", "caveats": caveats}
