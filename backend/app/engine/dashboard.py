"""Dashboard aggregates computed from stored results. Pure functions over the results payload."""

from __future__ import annotations

from typing import Any

from app.domain.similarity import METRICS
from app.domain.solution import format_term, solution_key, solution_terms

VALID = {"valid", "valid_no_solution"}


def _arm_kind(arm: str) -> str:
    return "role" if arm.startswith("role:") else arm


def build_dashboard(results: dict[str, Any], kind: str = "parsimonious", metric: str = "jaccard_terms",
                    policy: str = "union") -> dict[str, Any]:
    fn = METRICS[metric][0]
    runs = results["runs"]
    ref_run = next((r for r in runs if r["arm"] == "reference"), None)
    ref_terms = solution_terms(ref_run["solutions"][kind], policy) if ref_run and ref_run["solutions"] else None
    arms = [a for a in dict.fromkeys(r["arm"] for r in runs) if a != "reference"]

    matrix: list[dict[str, Any]] = []
    sims: list[dict[str, Any]] = []
    distinct: dict[str, set[str]] = {}
    term_counts: dict[str, dict[str, int]] = {}
    valid_n: dict[str, int] = {}
    for r in runs:
        if r["arm"] == "reference":
            continue
        ok = r["status"] in VALID and r["solutions"] is not None
        terms = solution_terms(r["solutions"][kind], policy) if ok else None
        matrix.append({"run_id": r["run_id"], "arm": r["arm"], "rep": r["mechanical_id"] or r["rep"] + 1,
                       "status": r["status"], "solution": solution_key(terms) if terms is not None else None})
        if terms is None:
            continue
        valid_n[r["arm"]] = valid_n.get(r["arm"], 0) + 1
        distinct.setdefault(r["arm"], set()).add(solution_key(terms))
        for t in terms:
            term_counts.setdefault(format_term(t), {}).setdefault(r["arm"], 0)
            term_counts[format_term(t)][r["arm"]] += 1
        if ref_terms is not None:
            sims.append({"run_id": r["run_id"], "arm": r["arm"], "score": fn(terms, ref_terms)})

    ref_paths = sorted(format_term(t) for t in ref_terms) if ref_terms is not None else []
    robustness = []
    for p in ref_paths:
        per_arm = {a: (term_counts.get(p, {}).get(a, 0) / valid_n[a] if valid_n.get(a) else None) for a in arms}
        role_shares = [v for a, v in per_arm.items() if a.startswith("role:") and v is not None]
        n_with = sum(1 for v in role_shares if v > 0)
        label = ("not evaluated" if not role_shares else "all roles" if n_with == len(role_shares)
                 else "one role only" if n_with == 1 else "some roles" if n_with else "no role")
        robustness.append({"path": p, "share_by_arm": per_arm, "across_roles": label})
    return {
        "kind": kind, "metric": metric, "metric_doc": METRICS[metric][1], "model_policy": policy,
        "arms": arms, "reference_solution": solution_key(ref_terms) if ref_terms is not None else None,
        "matrix": matrix, "robustness": robustness, "similarity": sims,
        "distinct_solutions": {a: len(distinct.get(a, ())) for a in arms}, "valid_runs": {a: valid_n.get(a, 0) for a in arms},
        "path_frequency": [{"path": p, "counts": c} for p, c in sorted(term_counts.items())],
    }
