import copy
import json

import pytest

from app.domain.validator import VarInfo, validate_decision
from tests.conftest import good_decision

CONDS = [VarInfo("A", "positive", 1, 7), VarInfo("B", "negative", 0, 100)]
OUT = VarInfo("Y", "positive", 0, 100)


def check(d, tol=0.0):
    return validate_decision(d if isinstance(d, str) else json.dumps(d), CONDS, OUT, tol)


def codes(res):
    return {e.code for e in res.errors}


def test_valid_passes_and_decision_unchanged():
    d = good_decision()
    res = check(d)
    assert res.ok and res.decision == d


def test_not_json():
    assert codes(check("here you go: {}")) == {"json_parse"}


def test_code_fence_is_not_stripped():
    assert codes(check("```json\n" + json.dumps(good_decision()) + "\n```")) == {"json_parse"}


@pytest.mark.parametrize("tok", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_constants_rejected(tok):
    txt = json.dumps(good_decision()).replace('"crossover": 4', f'"crossover": {tok}', 1)
    assert codes(check(txt)) == {"json_parse"}


def test_reversed_positive_ordering():
    d = good_decision()
    d["conditions"]["A"]["anchors"] = {"full_non_membership": 6, "crossover": 4, "full_membership": 2}
    assert codes(check(d)) == {"ordering"}


def test_positive_orientation_on_negative_variable_is_invalid():
    d = good_decision()
    d["conditions"]["B"]["anchors"] = {"full_non_membership": 20, "crossover": 50, "full_membership": 80}
    assert codes(check(d)) == {"ordering"}


def test_equal_anchors_rejected():
    d = good_decision()
    d["conditions"]["A"]["anchors"]["crossover"] = 2
    assert "ordering" in codes(check(d))


def test_boundary_values_allowed_at_zero_tolerance():
    d = good_decision()
    d["conditions"]["A"]["anchors"] = {"full_non_membership": 1, "crossover": 4, "full_membership": 7}
    assert check(d).ok


def test_outside_range_rejected_not_clamped():
    d = good_decision()
    d["conditions"]["A"]["anchors"]["full_membership"] = 7.0001
    res = check(d)
    assert codes(res) == {"range"} and res.decision is None


def test_tolerance_allows_near_range():
    d = good_decision()
    d["conditions"]["A"]["anchors"]["full_membership"] = 7.3  # range 6 * 0.1 = 0.6 pad
    assert check(d, tol=0.1).ok
    assert not check(d, tol=0.0).ok


def test_missing_condition():
    d = good_decision(); del d["conditions"]["B"]
    assert codes(check(d)) == {"schema"}


def test_missing_anchor():
    d = good_decision(); del d["outcome"]["anchors"]["crossover"]
    assert codes(check(d)) == {"schema"}


def test_extra_fields_rejected():
    d = good_decision(); d["notes"] = "hi"
    assert codes(check(d)) == {"schema"}
    d = good_decision(); d["conditions"]["A"]["extra"] = 1
    assert codes(check(d)) == {"schema"}


def test_string_anchor_rejected():
    d = good_decision(); d["conditions"]["A"]["anchors"]["crossover"] = "4"
    assert codes(check(d)) == {"schema"}


def test_boolean_anchor_rejected():
    d = good_decision(); d["conditions"]["A"]["anchors"]["crossover"] = True
    assert codes(check(d)) == {"schema"}


def test_empty_and_blank_rationale():
    d = good_decision(); d["conditions"]["A"]["rationale"]["crossover"] = ""
    assert codes(check(d)) == {"schema"}
    d = good_decision(); d["conditions"]["A"]["rationale"]["crossover"] = "   "
    assert codes(check(d)) == {"blank_rationale"}


@pytest.mark.parametrize("field,val", [("consistency_threshold", 1.01), ("consistency_threshold", -0.1),
                                        ("frequency_threshold", 0), ("frequency_threshold", 1.5)])
def test_truth_table_cutoff_limits(field, val):
    d = good_decision(); d["truth_table"][field] = val
    assert codes(check(d)) == {"schema"}


def test_pri_requires_rationale():
    d = good_decision(); d["truth_table"]["pri_threshold"] = 0.5
    assert codes(check(d)) == {"blank_rationale"}
    d["truth_table"]["pri_rationale"] = "because"
    assert check(d).ok


def test_input_not_mutated():
    d = good_decision(); before = copy.deepcopy(d)
    check(d)
    assert d == before


def test_multiple_errors_reported():
    d = good_decision()
    d["conditions"]["A"]["anchors"] = {"full_non_membership": 9, "crossover": 4, "full_membership": 2}
    res = check(d)
    assert codes(res) == {"ordering", "range"}


# ---- calibration kinds -------------------------------------------------------------------------------------

BP_OUT = VarInfo("Y", "positive", 4, 1913, "breakpoints")
PRE = [VarInfo("A", "positive", 0, 1, "precalibrated"), VarInfo("B", "positive", 0, 1, "precalibrated")]


def bp_decision(b0=0, b1=15, b2=90):
    r = {k: "because" for k in ("break_0", "break_33", "break_67")}
    return {"conditions": {}, "outcome": {"breakpoints": {"break_0": b0, "break_33": b1, "break_67": b2}, "rationale": r},
            "truth_table": {"consistency_threshold": 0.8, "frequency_threshold": 1, "pri_threshold": None,
                            "consistency_rationale": "c", "frequency_rationale": "f", "pri_rationale": None}}


def check_bp(d, tol=0.0, out=BP_OUT):
    return validate_decision(json.dumps(d), PRE, out, tol)


def test_published_breakpoints_are_valid_even_though_break_0_is_below_the_observed_minimum():
    assert check_bp(bp_decision(0, 15, 90)).ok  # no platform has 0 proposals: break_0 may sit just off the data


def test_precalibrated_conditions_must_not_appear_in_the_decision():
    d = bp_decision()
    d["conditions"]["A"] = {"anchors": {"full_non_membership": 0, "crossover": 0.5, "full_membership": 1},
                            "rationale": {k: "x" for k in ("full_non_membership", "crossover", "full_membership")}}
    assert codes(check_bp(d)) == {"schema"}


def test_breakpoint_ordering_follows_orientation():
    assert codes(check_bp(bp_decision(0, 90, 15))) == {"ordering"}
    assert codes(check_bp(bp_decision(0, 15, 15))) == {"ordering"}
    neg = VarInfo("Y", "negative", 4, 1913, "breakpoints")
    assert check_bp(bp_decision(500, 100, 20), out=neg).ok
    assert codes(check_bp(bp_decision(20, 100, 500), out=neg)) == {"ordering"}


def test_breakpoint_range_rules():
    assert codes(check_bp(bp_decision(0, 15, 5000))) == {"range"}        # b2 above the observed maximum
    assert codes(check_bp(bp_decision(0, 1, 90))) == {"range"}           # b1 below the observed minimum
    assert codes(check_bp(bp_decision(-5000, 15, 90))) == {"range"}      # b0 more than one range below the data
    assert check_bp(bp_decision(-100, 15, 90)).ok


def test_breakpoint_blank_rationale_and_missing_keys():
    d = bp_decision()
    d["outcome"]["rationale"]["break_33"] = "   "
    assert codes(check_bp(d)) == {"blank_rationale"}
    d = bp_decision()
    del d["outcome"]["breakpoints"]["break_67"]
    assert codes(check_bp(d)) == {"schema"}


def test_an_outcome_that_is_already_calibrated_cannot_be_asked_for():
    import pytest as _pytest

    with _pytest.raises(ValueError):
        validate_decision("{}", PRE, VarInfo("Y", "positive", 0, 1, "precalibrated"))
