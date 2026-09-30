import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Base, CallLog, Judgment, Run, RunConfig
from app.domain.mechanical import generate_mechanical_configs
from app.domain.prompt import RoleSpec, load_default_template
from app.engine.report import validation_report
from app.engine.runner import CostModel, EngineContext, run_batch
from app.llm.base import ProviderError, RateLimitError
from app.llm.mock import MockProvider
from tests.conftest import good_decision, good_text, make_vars

R_CALLS: list[dict] = []


def fake_r(inp):
    R_CALLS.append(inp)
    return {"status": "ok", "solutions": {}}


def make(provider, session, reps=1, cap=None, prices=None, roles=("Clerk",), generic=False, mech=()):
    R_CALLS.clear()
    cfg = RunConfig(template_version="v1", template_sha256="x", provider="mock", model="m", reps=reps)
    session.add(cfg); session.commit()
    ctx = EngineContext(provider, "m", {}, load_default_template(), make_vars(), "cases", 0.0,
                        fake_r, lambda d: {"decision": d}, CostModel(prices or {}), cap, sleep=lambda s: None)
    return cfg, ctx, [RoleSpec(r, "d") for r in roles], generic, list(mech)


@pytest.fixture
def session():
    e = create_engine("sqlite://"); Base.metadata.create_all(e)
    with Session(e) as s:
        yield s


def bad_text():
    d = good_decision(); d["conditions"]["A"]["anchors"]["full_membership"] = 99
    return json.dumps(d)


def run_all(provider, session, **kw):
    cfg, ctx, roles, gen, mech = make(provider, session, **kw)
    out = run_batch(session, ctx, cfg, roles, gen, mech)
    return cfg, out


def test_valid_first_try_goes_to_r_unaltered(session):
    p = MockProvider([good_text()])
    cfg, out = run_all(p, session)
    run = session.query(Run).one()
    assert out == "completed" and run.status == "valid" and len(run.attempts) == 1
    assert R_CALLS[0]["decision"] == good_decision()
    assert run.attempts[0].raw_response == good_text()


def test_one_retry_with_errors_appended_then_valid(session):
    p = MockProvider([bad_text(), good_text()])
    run_all(p, session)
    run = session.query(Run).one()
    assert run.status == "valid" and [a.attempt_kind for a in run.attempts] == ["first", "validation_retry"]
    assert "previous answer was rejected" not in p.prompts[0]
    assert "previous answer was rejected" in p.prompts[1] and "[range]" in p.prompts[1]
    assert run.attempts[0].validation_ok is False


def test_two_failures_is_invalid_and_never_reaches_r(session):
    p = MockProvider([bad_text(), bad_text(), good_text()])
    run_all(p, session)
    run = session.query(Run).one()
    assert run.status == "invalid" and len(run.attempts) == 2 and not R_CALLS
    assert session.query(Judgment).count() == 0
    assert run.attempts[1].raw_response == bad_text()  # raw output kept


def test_never_more_than_one_retry(session):
    p = MockProvider([bad_text()] * 5)
    run_all(p, session)
    assert len(p.prompts) == 2


def test_rate_limit_retries_are_separate_from_validation_retry(session):
    p = MockProvider([RateLimitError(), RateLimitError(), good_text()])
    run_all(p, session)
    run = session.query(Run).one()
    assert run.status == "valid" and len(run.attempts) == 1 and run.attempts[0].rate_limit_retries == 2
    assert session.query(CallLog).filter_by(kind="rate_limit_retry").count() == 2


def test_rate_limit_exhaustion_is_provider_error_not_invalid(session):
    p = MockProvider([RateLimitError()] * 20)
    run_all(p, session)
    assert session.query(Run).one().status == "provider_error"


def test_provider_error(session):
    run_all(MockProvider([ProviderError("auth")]), session)
    assert session.query(Run).one().status == "provider_error"
    assert session.query(CallLog).filter_by(kind="provider_error").count() == 1


def test_arms_generic_and_reps_and_report(session):
    seq = {"n": 0}

    def script(prompt):
        seq["n"] += 1
        return bad_text() if "Clerk" in prompt else good_text()

    cfg, out = run_all(MockProvider(script), session, reps=3, generic=True)
    rep = validation_report(session, cfg.id)
    assert rep["generic"]["invalid_rate"] == 0 and rep["role:Clerk"]["invalid_rate"] == 1.0
    assert rep["role:Clerk"]["failure_reasons"] == {"range": 3}
    assert rep["role:Clerk"]["first_attempt_failure_rate"] == 1.0
    assert session.query(Run).count() == 6


def test_generic_prompt_has_no_role(session):
    p = MockProvider([good_text()])
    run_all(p, session, roles=(), generic=True)
    assert "Your vantage point" not in p.prompts[0]


def test_spend_cap_halts_and_resume_completes(session):
    p = MockProvider(lambda prompt: good_text())
    cfg, ctx, roles, gen, mech = make(p, session, reps=4, cap=0.0001, prices={"m": (1e6, 1e6)})
    assert run_batch(session, ctx, cfg, roles, gen, mech) == "halted_cap"
    done = session.query(Run).filter(Run.status == "valid").count()
    assert 0 < done < 4
    ctx.spend_cap = None
    assert run_batch(session, ctx, cfg, roles, gen, mech) == "completed"
    assert session.query(Run).filter(Run.status == "valid").count() == 4


def test_cancel_and_resume(session):
    p = MockProvider(lambda prompt: good_text())
    cfg, ctx, roles, gen, mech = make(p, session, reps=3)
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] > 1

    assert run_batch(session, ctx, cfg, roles, gen, mech, cancel) == "cancelled"
    assert session.query(Run).filter(Run.status == "valid").count() == 1
    assert run_batch(session, ctx, cfg, roles, gen, mech) == "completed"
    assert len(p.prompts) == 3  # completed runs are not repeated


def test_mechanical_arm_goes_through_same_r_path(session):
    data = {"A": [float(i) for i in range(1, 8)], "B": [float(i) for i in range(0, 101, 15)], "Y": [float(i) for i in range(0, 101, 15)]}
    ref = {"A": {"full_non_membership": 2, "crossover": 4, "full_membership": 6},
           "B": {"full_non_membership": 80, "crossover": 50, "full_membership": 20},
           "Y": {"full_non_membership": 25, "crossover": 50, "full_membership": 75}}
    mech = generate_mechanical_configs(data, ref, {"A": "positive", "B": "negative", "Y": "positive"}, "Y",
                                       {"consistency_threshold": 0.8, "frequency_threshold": 2})
    cfg, out = run_all(MockProvider([]), session, roles=(), mech=mech)
    runs = session.query(Run).all()
    assert len(runs) == len(mech) and all(r.arm == "mechanical" for r in runs)
    assert len(R_CALLS) == sum(1 for m in mech if m.decision is not None)
    assert not any(r.attempts for r in runs)  # no LLM involved


def test_r_statuses_propagate(session):
    R_CALLS.clear()
    cfg, ctx, roles, gen, mech = make(MockProvider([good_text()]), session)
    ctx.pipeline_fn = lambda i: {"status": "valid_no_solution"}
    run_batch(session, ctx, cfg, roles, gen, mech)
    assert session.query(Run).one().status == "valid_no_solution"
