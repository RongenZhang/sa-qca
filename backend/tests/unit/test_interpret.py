"""Interpretation facts and rule-based narrative, on hand-built results where the right answer is known."""

import pytest

from app.engine.interpret import build_facts, template_narrative


def run(i, arm, sols, status="valid", anchors=None, cutoffs=None, kind="parsimonious"):
    return {"run_id": i, "arm": arm, "rep": 0, "status": status, "mechanical_id": None, "attempts": 1, "anchors": anchors,
            "cutoffs": cutoffs or {"consistency_threshold": 0.8, "frequency_threshold": 1, "pri_threshold": None},
            "solutions": ({"complex": sols, "parsimonious": sols, "intermediate": []} if status in ("valid", "valid_no_solution") else None)}


def anchors(x_shift, direction_scale=100.0):
    base = {"full_non_membership": 20, "crossover": 50, "full_membership": 80}
    return {"X": {k: v + x_shift for k, v in base.items()}, "outcome": dict(base)}


PROJ = {"name": "P", "reference": {"X": {"full_non_membership": 20, "crossover": 50, "full_membership": 80},
                                    "Y": {"full_non_membership": 20, "crossover": 50, "full_membership": 80}},
        "variables": [{"name": "X", "role": "condition", "direction": "positive", "calibration": "direct", "stats": {"min": 0, "max": 100}},
                      {"name": "Z", "role": "condition", "direction": "positive", "calibration": "precalibrated", "stats": {"min": 0, "max": 1}},
                      {"name": "Y", "role": "outcome", "direction": "positive", "calibration": "direct", "stats": {"min": 0, "max": 100}}]}
BOTH, ONLY_A = [["A", "B*C"]], [["A"]]


def results(extra=(), provider="anthropic"):
    runs = [run(1, "reference", BOTH),
            run(2, "role:Strict", ONLY_A, anchors=anchors(+10)), run(3, "role:Strict", ONLY_A, anchors=anchors(+10)),
            run(4, "role:Lenient", BOTH, anchors=anchors(-10)), run(5, "role:Lenient", BOTH, anchors=anchors(-10)),
            run(6, "role:Typical", BOTH, anchors=anchors(0)), run(7, "role:Typical", [["A", "B*C", "D"]], anchors=anchors(1)),
            run(8, "generic", BOTH), run(9, "mechanical", BOTH), run(10, "mechanical", ONLY_A), *extra]
    return {"runs": runs, "project": PROJ, "config": {"provider": provider, "model": "m", "reps": 2}}


def path(f, p):
    return next(x for x in f["paths"] if x["path"] == p)


def test_robust_and_contested_paths_are_classified_from_the_readings():
    f = build_facts(results())
    assert f["reference"]["solution"] == "A + B*C"
    assert path(f, "A")["classification"] == "robust" and path(f, "A")["present_under"] == ["Strict", "Lenient", "Typical"]
    bc = path(f, "B*C")
    assert bc["classification"] == "contested" and bc["present_under"] == ["Lenient", "Typical"] and bc["absent_under"] == ["Strict"]
    d = path(f, "D")  # in 1 of Typical's 2 runs: exactly half, which meets the "at least half of that reading's runs" bar
    assert d["in_analyst_solution"] is False and d["classification"] == "stakeholder-specific" and d["present_under"] == ["Typical"]


def test_a_path_below_the_half_of_runs_bar_is_rare_not_present():
    extra = [run(11, "role:Typical", BOTH, anchors=anchors(0))]  # Typical now has 3 runs; D is in only 1 of 3
    d = path(build_facts(results(extra)), "D")
    assert d["classification"] == "rare" and d["present_under"] == [] and d["absent_under"] == ["Strict", "Lenient", "Typical"]


def test_a_tie_between_equally_common_solutions_is_broken_alphabetically_not_by_run_order():
    a = build_facts(results())
    r = results()
    r["runs"].sort(key=lambda x: -x["run_id"])  # same runs, reversed order
    b = build_facts(r)
    assert a["agreement"]["modal_solutions"] == b["agreement"]["modal_solutions"]
    assert a["agreement"]["modal_solutions"]["Typical"] == "A + B*C"


def test_a_path_present_under_exactly_one_of_three_readings_is_stakeholder_specific():
    extra = [run(11, "role:Strict", [["A", "E"]]), run(12, "role:Strict", [["A", "E"]])]
    r = results(extra)
    r["runs"] = [x if x["run_id"] != 7 else {**x, "solutions": {"complex": BOTH, "parsimonious": BOTH, "intermediate": []}} for x in r["runs"]]  # remove D
    f = build_facts(r)  # Strict now has 4 runs, 2 with E: share 0.5 = present
    e = path(f, "E")
    assert e["present_under"] == ["Strict"] and e["classification"] == "stakeholder-specific" and e["in_analyst_solution"] is False


def test_calibration_stance_is_relative_to_the_analyst_and_orientation_aware():
    f = build_facts(results())
    prof = {s["label"]: {c["variable"]: c for c in s["calibration"]} for s in f["sources"] if s["kind"] == "stakeholder"}
    assert prof["Strict"]["X"]["shift_pct_of_scale"] == 10.0 and prof["Strict"]["X"]["stance"] == "stricter"
    assert prof["Lenient"]["X"]["stance"] == "more lenient" and prof["Typical"]["X"]["stance"] == "similar"
    assert "Z" not in prof["Strict"]  # an already-calibrated condition has nothing to compare
    neg = {**PROJ, "variables": [{**PROJ["variables"][0], "direction": "negative"}, *PROJ["variables"][1:]]}
    fn = build_facts({**results(), "project": neg})
    s = next(x for x in fn["sources"] if x["label"] == "Strict")
    assert s["calibration"][0]["stance"] == "more lenient"  # a higher threshold on a negatively oriented variable is a lower bar


def test_the_calibration_contrast_points_at_where_the_losing_readings_differ():
    f = build_facts(results())
    c = path(f, "B*C")["calibration_contrast"][0]
    assert c["variable"] == "X" and c["shift_where_absent"] == 10.0 and c["shift_where_present"] == pytest.approx(-4.5, abs=0.6)


def test_agreement_and_stability_and_mechanical_share():
    f = build_facts(results())
    ag = f["agreement"]
    assert ag["n_stakeholders"] == 3 and ag["modal_solutions"]["Strict"] == "A" and ag["modal_solutions"]["Lenient"] == "A + B*C"
    assert ag["between_readings_same_solution_share"] == pytest.approx(1 / 3)  # only Lenient and Typical agree
    assert next(s for s in f["sources"] if s["label"] == "Typical")["modal_share"] == 0.5
    assert f["mechanical_matches_analyst_share"] == 0.5 and f["stakeholders_match_analyst"] == ["Lenient", "Typical"]


def test_invalid_runs_are_counted_and_excluded_from_the_readings():
    f = build_facts(results([run(11, "role:Strict", None, status="invalid")]))
    s = next(x for x in f["sources"] if x["label"] == "Strict")
    assert s["n_runs"] == 3 and s["n_valid"] == 2 and s["n_invalid"] == 1 and s["invalid_rate"] == pytest.approx(1 / 3)


def test_without_a_reference_there_is_no_analyst_only_class_and_no_similarity():
    r = results()
    r["runs"] = [x for x in r["runs"] if x["arm"] != "reference"]
    f = build_facts(r)
    assert f["reference"] is None and all(not p["in_analyst_solution"] for p in f["paths"]) and f["mechanical_matches_analyst_share"] is None
    assert all(s["similarity_to_analyst_mean"] is None for s in f["sources"])
    assert "appear under every reading" in template_narrative(f)["headline"]


def test_a_path_in_the_analyst_solution_that_no_stakeholder_finds_is_analyst_only():
    r = results()
    r["runs"] = [x if x["arm"] == "reference" or not x["arm"].startswith("role:") else {**x, "solutions": {"complex": ONLY_A, "parsimonious": ONLY_A, "intermediate": []}} for x in r["runs"]]
    assert path(build_facts(r), "B*C")["classification"] == "analyst-only"


def test_template_narrative_says_what_holds_and_what_depends_on_the_reading():
    n = template_narrative(build_facts(results()))
    assert n["headline"].startswith("Of the 2 paths in the analyst's parsimonious solution, 1 holds under all 3 stakeholder readings and 1 depends on whose reading is used")
    assert [x["path"] for x in n["robust_findings"]] == ["A"] and "does not depend on which stakeholder" in n["robust_findings"][0]["meaning"]
    c = n["contested_findings"][0]
    assert c["path"] == "B*C" and c["holds_under"] == ["Lenient", "Typical"] and c["fails_under"] == ["Strict"]
    assert "descriptive" in c["meaning"] and "cannot show that the calibration difference caused" in c["meaning"]
    st = {p["stakeholder"]: p for p in n["stakeholder_perspectives"]}
    assert "a stricter bar than the analyst on X (+10% of the scale)" in st["Strict"]["reading"] and "Does not support B*C" in st["Strict"]["implication"]
    assert "Agrees with the analyst's solution" in st["Lenient"]["implication"]
    assert "variable across its repetitions" in st["Typical"]["reading"]
    assert "stakeholder readings moved the solution more than the mechanical perturbation" in n["implications"] or "no more disruptive" in n["implications"]


def test_caveats_are_honest_about_scripted_versus_model_readings():
    scripted = template_narrative(build_facts(results(provider="demo-mock")))
    assert "scripted stand-in" in scripted["caveats"][0] and "says nothing about real stakeholders" in scripted["caveats"][0]
    real = template_narrative(build_facts(results()))
    assert "not evidence about what real stakeholders think" in real["caveats"][0]
    assert any("run-to-run noise" in c for c in real["caveats"])


def test_no_valid_stakeholder_reading_means_nothing_to_interpret():
    n = template_narrative(build_facts({"runs": [run(1, "reference", BOTH), run(2, "role:A", None, status="invalid")], "project": PROJ, "config": {"provider": "x", "model": "m", "reps": 1}}))
    assert "nothing yet to interpret" in n["headline"] and n["robust_findings"] == []
