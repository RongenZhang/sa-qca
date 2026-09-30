import math

import pytest

from app.domain.similarity import jaccard_terms, literal_jaccard, subset_aware
from app.domain.solution import format_term, parse_term, solution_key, solution_terms
from app.engine.dashboard import build_dashboard


def T(*exprs):
    return frozenset(parse_term(e) for e in exprs)


def test_parse_negation_and_order_invariance():
    assert parse_term("A*~B") == parse_term("~B*A")
    assert parse_term("~A") != parse_term("A")
    assert format_term(parse_term("B*~A")) == "~A*B"
    with pytest.raises(ValueError):
        parse_term("A**B")


def test_solution_terms_policy():
    models = [["A*B"], ["A*C"]]
    assert solution_terms(models) == T("A*B", "A*C")
    assert solution_terms(models, "first") == T("A*B")
    assert solution_terms([]) == frozenset() and solution_key(frozenset()) == "(none)"
    with pytest.raises(ValueError):
        solution_terms(models, "nope")


def test_jaccard_values():
    assert jaccard_terms(T("A*B", "C"), T("A*B", "C")) == 1.0
    assert jaccard_terms(T("A*B"), T("A*B*C")) == 0.0
    assert math.isclose(jaccard_terms(T("A", "B"), T("B", "C")), 1 / 3)
    assert jaccard_terms(frozenset(), frozenset()) == 1.0 and jaccard_terms(T("A"), frozenset()) == 0.0


def test_negation_is_a_different_literal():
    assert jaccard_terms(T("A*B"), T("~A*B")) == 0.0 and literal_jaccard(T("A"), T("~A")) == 0.0


def test_subset_aware_gives_partial_credit_and_is_symmetric():
    a, b = T("A*B"), T("A*B*C")
    assert math.isclose(subset_aware(a, b), 2 / 3)
    assert subset_aware(a, b) == subset_aware(b, a)
    assert subset_aware(T("A"), T("B")) == 0.0 and subset_aware(a, a) == 1.0


def test_literal_jaccard():
    assert math.isclose(literal_jaccard(T("A*B"), T("A*C")), 1 / 3)


def _run(i, arm, sol, status="valid", rep=0, mech=None):
    return {"run_id": i, "arm": arm, "rep": rep, "status": status, "mechanical_id": mech, "attempts": 1, "anchors": None,
            "solutions": {"complex": [], "parsimonious": sol, "intermediate": []} if status != "invalid" else None}


def test_dashboard_robustness_similarity_and_invalid_handling():
    runs = [
        _run(1, "reference", [["A", "B*C"]]),
        _run(2, "role:X", [["A"]]), _run(3, "role:X", [["A", "B*C"]], rep=1),
        _run(4, "role:Y", [["A"]]), _run(5, "role:Y", [], "invalid", rep=1),
        _run(6, "generic", [["D"]]),
        _run(7, "mechanical", [["A", "B*C"]], mech="m1"),
    ]
    d = build_dashboard({"runs": runs})
    assert d["reference_solution"] == "A + B*C" and "reference" not in d["arms"]
    rob = {r["path"]: r for r in d["robustness"]}
    assert rob["A"]["share_by_arm"]["role:X"] == 1.0 and rob["A"]["across_roles"] == "all roles"
    assert rob["B*C"]["share_by_arm"]["role:X"] == 0.5 and rob["B*C"]["across_roles"] == "one role only"
    assert rob["B*C"]["share_by_arm"]["role:Y"] == 0.0  # invalid run excluded from the denominator
    assert d["valid_runs"]["role:Y"] == 1
    scores = {s["run_id"]: s["score"] for s in d["similarity"]}
    assert 5 not in scores and scores[3] == 1.0 and scores[2] == 0.5 and scores[6] == 0.0
    assert d["distinct_solutions"]["role:X"] == 2
    assert any(m["status"] == "invalid" and m["solution"] is None for m in d["matrix"])


def test_dashboard_without_reference():
    d = build_dashboard({"runs": [_run(1, "generic", [["A"]])]})
    assert d["reference_solution"] is None and d["similarity"] == [] and d["robustness"] == []
