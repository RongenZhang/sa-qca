"""Agent runner (protocol steps 2, 4, 5).

Rules enforced here:
* model output is passed on exactly as parsed; never edited;
* exactly one validation retry, with the validation errors appended to the prompt;
* a second failure is an `invalid` judgment; it is kept, and never sent to R;
* rate-limit retries are separate from the validation retry, and logged separately.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import CallLog, Judgment, RResult, Run, RunAttempt, RunConfig
from app.domain.mechanical import MechanicalConfig
from app.domain.prompt import RoleSpec, VariableSpec, prompt_hash, render_prompt
from app.domain.validator import VarInfo, validate_decision
from app.llm.base import LLMProvider, LLMResponse, ProviderError, RateLimitError


class CapExceeded(Exception):
    """Spending cap reached; the batch halts and can be resumed."""


@dataclass
class CostModel:
    """USD per million tokens as (input, output). Empty by default: no invented prices."""

    prices: dict[str, tuple[float, float]] = field(default_factory=dict)

    def estimate(self, model: str, tin: int | None, tout: int | None) -> float | None:
        if model not in self.prices or tin is None or tout is None:
            return None
        pi, po = self.prices[model]
        return (tin * pi + tout * po) / 1_000_000


@dataclass
class EngineContext:
    provider: LLMProvider
    model: str
    sampling: dict[str, Any]
    template: str
    variables: list[VariableSpec]
    case_description: str
    tolerance: float
    pipeline_fn: Callable[[dict[str, Any]], dict[str, Any]]
    r_input_fn: Callable[[dict[str, Any]], dict[str, Any]]
    cost_model: CostModel = field(default_factory=CostModel)
    spend_cap: float | None = None
    spent: float = 0.0
    max_rate_limit_retries: int = 5
    backoff_base: float = 1.0
    sleep: Callable[[float], None] = time.sleep

    @property
    def cond_infos(self) -> list[VarInfo]:
        return [
            VarInfo(v.name, v.direction, v.stats["min"], v.stats["max"])
            for v in self.variables
            if v.role == "condition"
        ]

    @property
    def outcome_info(self) -> VarInfo:
        o = next(v for v in self.variables if v.role == "outcome")
        return VarInfo(o.name, o.direction, o.stats["min"], o.stats["max"])


def _call(session: Session, ctx: EngineContext, run: Run, attempt: RunAttempt) -> LLMResponse | None:
    for n in range(ctx.max_rate_limit_retries + 1):
        if ctx.spend_cap is not None and ctx.spent >= ctx.spend_cap:
            raise CapExceeded(f"spend {ctx.spent} reached cap {ctx.spend_cap}")
        try:
            return ctx.provider.complete(attempt.rendered_prompt, model=ctx.model, sampling=ctx.sampling)
        except RateLimitError as e:
            session.add(CallLog(run_id=run.id, attempt_id=attempt.id, kind="rate_limit_retry", detail=str(e)))
            attempt.rate_limit_retries += 1
            session.flush()
            if n == ctx.max_rate_limit_retries:
                break
            ctx.sleep(e.retry_after if e.retry_after is not None else ctx.backoff_base * 2**n)
        except ProviderError as e:
            session.add(CallLog(run_id=run.id, attempt_id=attempt.id, kind="provider_error", detail=str(e)))
            break
    return None


def execute_agent_run(session: Session, ctx: EngineContext, run: Run, role: RoleSpec | None) -> None:
    errors: list[str] | None = None
    decision: dict[str, Any] | None = None
    for kind in ("first", "validation_retry"):
        prompt = render_prompt(ctx.template, ctx.variables, ctx.case_description, role, errors)
        attempt = RunAttempt(
            run_id=run.id, attempt_kind=kind, rendered_prompt=prompt, prompt_sha256=prompt_hash(prompt),
            provider=ctx.provider.name, sampling=ctx.sampling,
        )
        session.add(attempt)
        session.flush()
        resp = _call(session, ctx, run, attempt)
        if resp is None:
            run.status = "provider_error"
            session.commit()
            return
        attempt.model_id = resp.model_id
        attempt.raw_response = resp.text
        attempt.tokens_in, attempt.tokens_out = resp.tokens_in, resp.tokens_out
        attempt.est_cost = ctx.cost_model.estimate(ctx.model, resp.tokens_in, resp.tokens_out)
        ctx.spent += attempt.est_cost or 0.0
        result = validate_decision(resp.text, ctx.cond_infos, ctx.outcome_info, ctx.tolerance)
        attempt.validation_ok = result.ok
        attempt.validation_errors = [e.__dict__ for e in result.errors]
        session.flush()
        if result.ok:
            decision = result.decision
            session.add(Judgment(run_id=run.id, source="agent", attempt_id=attempt.id, decision=decision or {}))
            session.flush()
            _run_r(session, ctx, run)
            session.commit()
            return
        errors = [f"[{e.code}] {e.path}: {e.message}" for e in result.errors]
    run.status = "invalid"
    session.commit()


def _run_r(session: Session, ctx: EngineContext, run: Run) -> None:
    j = run.judgment or session.query(Judgment).filter_by(run_id=run.id).one()
    r_in = ctx.r_input_fn(j.decision)
    r_out = ctx.pipeline_fn(r_in)
    session.add(RResult(judgment_id=j.id, r_input=r_in, r_output=r_out))
    status = r_out.get("status", "r_error")
    run.status = "valid" if status == "ok" else status


def execute_mechanical_run(session: Session, ctx: EngineContext, run: Run, cfg: MechanicalConfig) -> None:
    if cfg.decision is None:
        run.status = "invalid"  # perturbation broke structure; recorded, not repaired
        session.add(CallLog(run_id=run.id, kind="mechanical_skipped", detail=cfg.skipped_reason or ""))
        session.commit()
        return
    session.add(Judgment(run_id=run.id, source="mechanical", decision=cfg.decision))
    session.flush()
    _run_r(session, ctx, run)
    session.commit()


TERMINAL = {"valid", "invalid", "r_error", "valid_no_solution", "provider_error", "ok"}


def run_batch(
    session: Session,
    ctx: EngineContext,
    config: RunConfig,
    roles: list[RoleSpec],
    include_generic: bool,
    mechanical: list[MechanicalConfig],
    cancel: Callable[[], bool] = lambda: False,
) -> str:
    """Executes (or resumes) a batch. Returns 'completed', 'cancelled' or 'halted_cap'."""
    if session.query(Run).filter_by(run_config_id=config.id).count() == 0:
        for rep in range(config.reps):  # interleave arms so a halt leaves balanced data
            for r in roles:
                session.add(Run(run_config_id=config.id, arm=f"role:{r.name}", rep_index=rep))
            if include_generic:
                session.add(Run(run_config_id=config.id, arm="generic", rep_index=rep))
        for i, m in enumerate(mechanical):
            session.add(Run(run_config_id=config.id, arm="mechanical", rep_index=i, mechanical_id=m.id))
        session.commit()
    by_name = {r.name: r for r in roles}
    mech = {m.id: m for m in mechanical}
    for run in session.query(Run).filter_by(run_config_id=config.id).order_by(Run.id).all():
        if run.status in TERMINAL and run.status != "provider_error":
            continue
        if cancel():
            return "cancelled"
        run.status = "pending"
        try:
            if run.arm == "mechanical":
                execute_mechanical_run(session, ctx, run, mech[run.mechanical_id or ""])
            elif run.arm == "generic":
                execute_agent_run(session, ctx, run, None)
            else:
                execute_agent_run(session, ctx, run, by_name[run.arm.removeprefix("role:")])
        except CapExceeded:
            session.commit()
            return "halted_cap"
    return "completed"
