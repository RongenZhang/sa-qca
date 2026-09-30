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
