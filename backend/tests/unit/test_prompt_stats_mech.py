import math

from app.domain.mechanical import MechanicalParams, generate_mechanical_configs
from app.domain.prompt import (
    RoleSpec,
    VariableSpec,
    load_default_template,
    prompt_hash,
    prompt_warnings,
    render_prompt,
)
from app.domain.stats import describe, percentile_rank, quantile
from tests.conftest import make_vars


def test_describe_matches_known_values():
    d = describe([1, 2, 3, 4, 5])
    assert (d["min"], d["max"], d["median"], d["mean"], d["q1"], d["q3"]) == (1, 5, 3, 3, 2, 4)
    assert sum(b["count"] for b in d["histogram"]) == 5


def test_quantile_and_rank():
    assert quantile([1, 2, 3, 4], 0.5) == 2.5
    assert percentile_rank([1, 2, 3, 4], 2) == 50.0


def test_generic_prompt_has_no_role_block():
    p = render_prompt(load_default_template(), make_vars(), "cases")
    assert "Your vantage point" not in p and "construct construct" not in p
    assert "A construct" in p and "A instrument" in p and "Histogram" in p


def test_role_prompt_and_only_difference_is_role_block():
    t, v = load_default_template(), make_vars()
    with_role = render_prompt(t, v, "cases", RoleSpec("Clerk", "Front-line view"))
    generic = render_prompt(t, v, "cases")
    assert "Clerk" in with_role and "Front-line view" in with_role
    assert with_role.replace(with_role[with_role.index("\n## Your vantage point"):with_role.index("\n## The phenomenon")], "") == generic


def test_retry_prompt_appends_errors():
    p = render_prompt(load_default_template(), make_vars(), "c", None, ["[ordering] $.x: bad"])
    assert "previous answer was rejected" in p and "[ordering] $.x: bad" in p
    assert "rejected" not in render_prompt(load_default_template(), make_vars(), "c")


def test_prompt_never_contains_raw_rows_and_is_deterministic():
    t, v = load_default_template(), make_vars()
    assert prompt_hash(render_prompt(t, v, "c")) == prompt_hash(render_prompt(t, v, "c"))


def test_warn_on_empty_definition_or_instrument():
    v = make_vars()
    v[0] = VariableSpec("A", "condition", "positive", " ", "", "u", v[0].stats)
    w = prompt_warnings(v)
    assert len(w) == 2 and all(x.startswith("A:") for x in w)


DATA = {"X": [float(i) for i in range(1, 101)], "Y": [float(i) for i in range(1, 101)]}
REF = {"X": {"full_non_membership": 20, "crossover": 50, "full_membership": 80},
       "Y": {"full_non_membership": 20, "crossover": 50, "full_membership": 80}}
TT = {"consistency_threshold": 0.8, "frequency_threshold": 1, "pri_threshold": None}


def gen(**kw):
    return generate_mechanical_configs(DATA, REF, {"X": "positive", "Y": "positive"}, "Y", TT, **kw)


def test_mechanical_is_deterministic_and_shifts_are_percentile_based():
    a, b = gen(), gen()
    assert [c.decision for c in a] == [c.decision for c in b]
    up = next(c for c in a if c.id == "joint_shift_+5")
    assert math.isclose(up.decision["conditions"]["X"]["anchors"]["crossover"], 55.0, abs_tol=1.0)
    assert all("mechanical" in r for r in up.decision["outcome"]["rationale"].values())


def test_mechanical_reference_anchors_untouched_for_cutoff_configs():
    c = next(c for c in gen() if c.id == "consistency_+0.05")
    assert c.decision["conditions"]["X"]["anchors"] == REF["X"]
    assert c.decision["truth_table"]["consistency_threshold"] == 0.85


def test_mechanical_out_of_bound_cutoffs_skipped_with_reason():
    c = generate_mechanical_configs(DATA, REF, {"X": "positive", "Y": "positive"}, "Y",
                                    {"consistency_threshold": 0.98, "frequency_threshold": 1})
    skipped = {x.id: x.skipped_reason for x in c if x.decision is None}
    assert skipped["consistency_+0.05"] and skipped["frequency_-1"]


def test_mechanical_ordering_breaks_are_skipped_not_repaired():
    ref = {"X": {"full_non_membership": 49, "crossover": 50, "full_membership": 51},
           "Y": dict(REF["Y"])}
    cfgs = generate_mechanical_configs(DATA, ref, {"X": "positive", "Y": "positive"}, "Y", TT,
                                       MechanicalParams(percentile_shifts=(), crossover_nudges=(10.0,),
                                                        consistency_shifts=(), frequency_shifts=()))
    bad = next(c for c in cfgs if c.id == "crossover_one_X_+10")
    assert bad.decision is None and "ordering" in bad.skipped_reason


def test_skaaning_factorial_size_and_outcome_untouched():
    from app.domain.mechanical import generate_skaaning_configs

    data = {"X": [float(i) for i in range(1, 101)], "Z": [float(i) for i in range(1, 101)], "Y": [float(i) for i in range(1, 101)]}
    ref = {"X": REF["X"], "Z": REF["X"], "Y": REF["Y"]}
    cfgs = generate_skaaning_configs(data, ref, {"X": "positive", "Z": "positive", "Y": "positive"}, "Y", TT)
    fact = [c for c in cfgs if c.perturbation["kind"] == "skaaning_factorial"]
    assert len(fact) == 3**2 - 1
    assert all(c.decision["outcome"]["anchors"] == ref["Y"] for c in fact)
    hi = next(c for c in fact if c.perturbation["levels"] == {"X": 1, "Z": 0})
    assert hi.decision["conditions"]["X"]["anchors"]["crossover"] == 50 + 0.05 * 99
    assert hi.decision["conditions"]["Z"]["anchors"] == ref["Z"]
    assert {c.id for c in cfgs if c.perturbation["kind"] != "skaaning_factorial"} == {"consistency_-0.1", "consistency_+0.1", "frequency_+1"}


def test_case_description_warnings():
    from app.domain.prompt import case_description_warnings

    assert "empty" in case_description_warnings("  ")[0]
    assert "short" in case_description_warnings("x" * 100)[0]
    assert case_description_warnings("x" * 450) == []


def test_demo_prompt_does_not_leak_the_built_in_routes():
    """The demo's construction note must stay out of anything an agent reads."""
    from app.demo import load_demo

    d = load_demo()
    prompt = render_prompt(load_default_template(), d["variables"], d["project"]["case_description"], RoleSpec("R", "d"))
    for leak in ("by construction", "two routes", "route", "low trust", "Synthetic", "synthetic"):
        assert leak not in prompt, leak
    assert len(d["project"]["case_description"]) > 600 


def test_prompt_uses_configurational_language_and_asks_for_substantive_rationales():
    p = render_prompt(load_default_template(), make_vars(), "cases", RoleSpec("Clerk", "Front-line view"))
    assert "## Conditions and outcome" in p and "## Variables" not in p
    assert "### A: a condition" in p and "### Y: the outcome" in p
    assert "each condition and the outcome is a set" in p
    assert "LESS membership in this set" in p  # B is negatively oriented in make_vars
    assert "substantive reasoning" in p and "not acceptable" in p
    assert "variable" not in p.replace("variables", "").lower().replace("a variable", "")  # no 'variable' vocabulary


def test_v1_template_still_loads_for_earlier_runs():
    from app.domain.prompt import load_template

    assert "## Variables" in load_template("default_v1")
    import pytest

    with pytest.raises(ValueError):
        load_template("../secrets")


def test_scripted_rationales_are_substantive_and_use_the_conditions_own_words():
    import json

    from app.demo import DemoProvider

    p = DemoProvider()
    d = p.demo
    prompt = render_prompt(load_default_template(), d["variables"], d["project"]["case_description"], RoleSpec("Independent IT consultant", "Advises firms."))
    dec = json.loads(p.complete(prompt, model="m", sampling={}).text)
    for name, block in dec["conditions"].items():
        for k, text in block["rationale"].items():
            assert len(text.split()) > 60, (name, k)
            assert "empirical check" in text
    trust = dec["conditions"]["TRUST"]["rationale"]["crossover"]
    assert "managerial trust in the technology vendor" in trust and "7-point Likert" in trust
    tt = dec["truth_table"]
    assert "60 cases and 3 conditions" in tt["frequency_rationale"] and len(tt["consistency_rationale"].split()) > 40


def _kinds_vars():
    from app.domain.prompt import VariableSpec
    from app.domain.stats import describe

    def v(name, role, kind, vals, direction="positive"):
        return VariableSpec(name, role, direction, f"{name} construct", f"{name} how measured", "", describe(vals), kind)

    return [v("A", "condition", "precalibrated", [0, 0.33, 0.67, 1, 0.67]), v("B", "condition", "direct", [1, 2, 3, 4, 5, 6, 7]),
            v("Y", "outcome", "breakpoints", [4, 7, 15, 40, 72, 90, 101, 1913])]


def test_v3_prompt_marks_fixed_sets_and_names_the_two_ways_to_calibrate():
    p = render_prompt(load_default_template(), _kinds_vars(), "cases", RoleSpec("R", "d"))
    assert "FIXED: this set is already calibrated" in p and "you must NOT calibrate it" in p
    assert "YOU CALIBRATE THIS SET WITH BREAKPOINTS" in p and "YOU CALIBRATE THIS SET WITH THREE ANCHORS" in p
    assert "break_33" in p and "LOWER of the two scores" in p
    # the schema in the prompt omits the fixed condition and asks breakpoints for the outcome
    schema = p[p.index("{\n  \"$schema\""):]
    assert '"A"' not in schema.split('"required"')[2] and '"break_0"' in schema
    # the fixed set shows its membership distribution but no raw histogram
    a_block = p[p.index("### A:"):p.index("### B:")]
    assert "Histogram" not in a_block and "Distribution of the membership scores" in a_block


def test_schema_rejects_asking_for_a_fixed_outcome():
    import pytest

    from app.domain.schema import build_decision_schema

    with pytest.raises(ValueError):
        build_decision_schema([("A", "direct")], "precalibrated")


def test_all_earlier_template_versions_still_load():
    from app.domain.prompt import load_template

    for v in ("default_v1", "default_v2", "default_v3"):
        assert load_template(v)


def test_skaaning_with_breakpoint_outcome_and_only_fixed_conditions_perturbs_the_outcome():
    from app.domain.mechanical import SkaaningParams, generate_skaaning_configs

    counts = [4, 6, 7, 15, 27, 40, 47, 51, 72, 77, 87, 100, 157, 1913]
    ref = {"Y": {"break_0": 0, "break_33": 15, "break_67": 90}}  # no calibrated conditions at all
    cfgs = generate_skaaning_configs({"Y": [float(c) for c in counts]}, ref, {"Y": "positive"}, "Y",
                                     {"consistency_threshold": 0.8, "frequency_threshold": 1, "pri_threshold": 0.75},
                                     SkaaningParams(perturb_outcome=True), kinds={"Y": "breakpoints"})
    fact = [c for c in cfgs if c.perturbation["kind"] == "skaaning_factorial"]
    assert len(fact) == 2  # outcome lower and higher; no conditions to cross
    hi = next(c for c in fact if c.perturbation["outcome_level"] == 1)
    assert hi.decision["conditions"] == {}
    b = hi.decision["outcome"]["breakpoints"]
    assert b == {"break_0": 4.5, "break_33": 19.5, "break_67": 94.5}  # 5% of the 90-wide reference spread, not of the 1909 range
    assert set(hi.decision["outcome"]["rationale"]) == {"break_0", "break_33", "break_67"}
    assert "anchors" not in hi.decision["outcome"]


def test_skaaning_default_leaves_the_outcome_alone_when_there_are_calibrated_conditions():
    from app.domain.mechanical import generate_skaaning_configs

    data = {"X": [float(i) for i in range(1, 101)], "Y": [float(i) for i in range(1, 101)]}
    ref = {"X": {"full_non_membership": 20, "crossover": 50, "full_membership": 80}, "Y": {"break_0": 0, "break_33": 25, "break_67": 75}}
    cfgs = generate_skaaning_configs(data, ref, {"X": "positive", "Y": "positive"}, "Y",
                                     {"consistency_threshold": 0.8, "frequency_threshold": 1}, kinds={"Y": "breakpoints"})
    fact = [c for c in cfgs if c.perturbation["kind"] == "skaaning_factorial"]
    assert len(fact) == 2 and all(c.decision["outcome"]["breakpoints"] == ref["Y"] for c in fact)
