"""Run orchestration for the HTTP API: role approval, batch threads, results assembly."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app import config, rclient
from app.db.models import Base, CallLog, Judgment, RoleApproval, RResult, Run, RunConfig
from app.demo import DemoProvider
from app.domain.mechanical import MechanicalConfig, generate_skaaning_configs
from app.domain.prompt import DEFAULT_TEMPLATE_VERSION, RoleSpec, load_default_template, prompt_hash
from app.engine.report import validation_report
from app.engine.rinput import build_r_input
from app.engine.runner import CostModel, EngineContext, run_batch
from app.llm.base import LLMProvider
from app.projects import get_project, project_summary

REPO_ROOT = Path(__file__).resolve().parents[3]
_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None
BATCHES: dict[int, dict[str, Any]] = {}  # run_config_id -> {"state", "cancel"}


def init_db(url: str | None = None) -> None:
    global _engine, _SessionLocal
    url = url or os.environ.get("SA_QCA_DB", "sqlite:///sa_qca.sqlite")
    _engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(_engine)
    from sqlalchemy import inspect, text

    have = {c["name"] for c in inspect(_engine).get_columns("run_config")}
    with _engine.begin() as conn:  # older dev databases: add columns introduced later
        for col, ddl in (("project_id", "VARCHAR DEFAULT 'demo'"), ("project_snapshot", "JSON"), ("role_approval", "JSON"), ("owner", "VARCHAR")):
            if col not in have:
                conn.execute(text(f"ALTER TABLE run_config ADD COLUMN {col} {ddl}"))
    _SessionLocal = sessionmaker(_engine, expire_on_commit=False)


def session() -> Session:
    if _SessionLocal is None:
        init_db()
    assert _SessionLocal is not None
    return _SessionLocal()


def r_pipeline(payload: dict[str, Any]) -> dict[str, Any]:
    if os.environ.get("RSERVICE_URL"):
        return rclient.run_pipeline(payload)
    return rclient.run_pipeline_local(payload, str(REPO_ROOT / "rservice"))


def roles_hash(roles: list[dict[str, Any]]) -> str:
    canon = json.dumps([{"name": r["name"], "description": r["description"]} for r in roles], sort_keys=True)
    return hashlib.sha256(canon.encode()).hexdigest()


def approve_roles(roles: list[dict[str, Any]], approved_by: str) -> dict[str, Any]:
    roles = [r for r in roles if r["name"].strip()]
    if not roles:
        raise ValueError("at least one role is required")
    if len({r["name"] for r in roles}) != len(roles):
        raise ValueError("role names must be unique")
    h = roles_hash(roles)
    with session() as s:
        row = s.query(RoleApproval).filter_by(roles_hash=h).one_or_none()
        if row is None:
            row = RoleApproval(roles=roles, roles_hash=h, approved_by=approved_by or "unknown")
            s.add(row)
            s.commit()
        return {"roles_hash": h, "approved_by": row.approved_by, "approved_at": _iso(row.approved_at)}


def make_provider(kind: str, api_key: str | None, project: dict[str, Any], workspace_id: str | None = None) -> LLMProvider:
    if kind == "demo-mock":
        return DemoProvider(project)
    if kind == "anthropic":
        if not api_key:
            raise ValueError("an API key is required for the Anthropic provider")
        from app.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key, workspace_id=workspace_id)
    raise ValueError(f"unknown provider {kind}")


class Busy(Exception):
    """Too many runs in progress (public demo)."""


def _check_demo_limits(req: dict[str, Any], sid: str | None) -> None:
    if not config.demo_only():
        return
    if req["provider"] != "demo-mock":
        raise ValueError("this public demo uses scripted responses only; run the tool locally to use a real model")
    if req.get("project_id", "demo") != "demo":
        raise PermissionError("only the demo project is available on this public demo")
    if int(req["reps"]) > config.max_reps() or len(req["arms"].get("roles", [])) > config.max_roles():
        raise ValueError(f"the public demo allows at most {config.max_reps()} repetitions and {config.max_roles()} roles")
    running = [b for b in BATCHES.values() if b["state"] == "running"]
    if any(b.get("owner") == sid for b in running):
        raise Busy("you already have a run in progress; wait for it to finish")
    if len(running) >= config.max_concurrent_runs():
        raise Busy("the demo is busy; please try again in a minute")


def start_run(req: dict[str, Any], api_key: str | None, workspace_id: str | None = None, sid: str | None = None) -> int:
    _check_demo_limits(req, sid)
    if config.demo_only():
        api_key = workspace_id = None  # nothing a visitor sends is ever used or stored
    with session() as s0:
        demo = get_project(s0, req.get("project_id", "demo"))
    arms = req["arms"]
    if arms.get("mechanical") and not demo["has_reference"]:
        raise ValueError("the mechanical source needs the analyst's original anchors and cutoffs; add them in step 1")
    roles: list[RoleSpec] = []
    if arms.get("roles"):
        with session() as s:
            appr = s.query(RoleApproval).filter_by(roles_hash=req.get("role_set_hash", "")).one_or_none()
            if appr is None:
                raise PermissionError("roles must be approved before running")
            chosen = set(arms["roles"])
            roles = [RoleSpec(r["name"], r["description"]) for r in appr.roles if r["name"] in chosen]
    provider = make_provider(req["provider"], api_key, demo, workspace_id)
    template = load_default_template()
    prices = {}
    if req.get("price_in") is not None and req.get("price_out") is not None:
        prices = {req["model"]: (float(req["price_in"]), float(req["price_out"]))}
    sampling = {"temperature": req["temperature"]} if req.get("temperature") is not None else {}
    mech = generate_skaaning_configs(demo["data"], demo["reference"], demo["directions"], demo["outcome"],
                                     demo["reference_cutoffs"]) if arms.get("mechanical") else []
    ref_cfg = (MechanicalConfig("analyst_reference", "analyst's original specification", _reference_decision(demo), source="analyst")
               if demo["has_reference"] else None)
    snapshot = project_summary(demo)
    snapshot["dataset_sha256"] = demo["dataset_sha256"]
    approval = None
    if roles:
        with session() as s1:
            ap = s1.query(RoleApproval).filter_by(roles_hash=req.get("role_set_hash", "")).one()
            approval = {"roles_hash": ap.roles_hash, "approved_by": ap.approved_by, "approved_at": _iso(ap.approved_at)}
    with session() as s:
        cfg = RunConfig(
            owner=sid, project_snapshot=snapshot, role_approval=approval,
            project_id=req.get("project_id", "demo"), template_version=DEFAULT_TEMPLATE_VERSION, template_sha256=prompt_hash(template), provider=provider.name,
            model=req["model"], sampling=sampling, reps=int(req["reps"]), tolerance=float(req.get("tolerance", 0.0)),
            spend_cap=req.get("spend_cap"), roles=[r.__dict__ for r in roles],
            arms=[*(f"role:{r.name}" for r in roles), *(["generic"] if arms.get("generic") else []),
                  *(["mechanical"] if arms.get("mechanical") else [])],
            mechanical_params={"generator": "skaaning_factorial", "shift_fraction": 0.05},
        )
        s.add(cfg)
        s.commit()
        cfg_id = cfg.id
    BATCHES[cfg_id] = {"state": "running", "cancel": False, "owner": sid}

    def work() -> None:
        with session() as s:
            c = s.get(RunConfig, cfg_id)
            assert c is not None
            ctx = EngineContext(
                provider, req["model"], sampling, template, demo["variables"], demo["project"]["case_description"],
                float(req.get("tolerance", 0.0)), r_pipeline,
                lambda d: build_r_input(d, demo["data"], demo["directions"], demo["dir_exp"], demo["outcome"]),
                CostModel(prices), req.get("spend_cap"),
            )
            try:
                state = run_batch(s, ctx, c, roles, bool(arms.get("generic")), mech,
                                  lambda: bool(BATCHES.get(cfg_id, {}).get("cancel")), ref_cfg)
            except Exception as e:  # surface unexpected failures instead of hanging the UI
                state = f"error: {e}"
            if cfg_id in BATCHES:
                BATCHES[cfg_id]["state"] = state

    threading.Thread(target=work, daemon=True).start()
    return cfg_id


def _reference_decision(demo: dict[str, Any]) -> dict[str, Any]:
    keys = ("full_non_membership", "crossover", "full_membership")

    def block(n: str) -> dict[str, Any]:
        return {"anchors": dict(demo["reference"][n]), "rationale": {k: "analyst's original specification" for k in keys}}

    tt = demo["reference_cutoffs"]
    return {"conditions": {v.name: block(v.name) for v in demo["variables"] if v.role == "condition"},
            "outcome": block(demo["outcome"]),
            "truth_table": {"consistency_threshold": tt["consistency_threshold"], "frequency_threshold": tt["frequency_threshold"],
                            "pri_threshold": tt.get("pri_threshold"), "consistency_rationale": "analyst's original cutoff",
                            "frequency_rationale": "analyst's original cutoff",
                            "pri_rationale": "analyst's original cutoff" if tt.get("pri_threshold") is not None else None}}


def cancel_run(cfg_id: int) -> None:
    if cfg_id in BATCHES:
        BATCHES[cfg_id]["cancel"] = True


def status(cfg_id: int) -> dict[str, Any]:
    with session() as s:
        runs = s.query(Run).filter_by(run_config_id=cfg_id).all()
        counts: dict[str, int] = {}
        for r in runs:
            counts[r.status] = counts.get(r.status, 0) + 1
        perr = [d for (d,) in s.query(CallLog.detail).join(Run, CallLog.run_id == Run.id)
                .filter(Run.run_config_id == cfg_id, CallLog.kind == "provider_error").distinct().limit(3).all()]
        return {"state": BATCHES.get(cfg_id, {}).get("state", "unknown"), "provider_errors": perr, "total": len(runs),
                "done": len(runs) - counts.get("pending", 0), "status_counts": counts,
                "report": validation_report(s, cfg_id)}


def _models(block: dict[str, Any] | None) -> list[list[str]]:
    if not block:
        return []
    return [[t["expression"] for t in m["terms"]] for m in block.get("models", [])]


def results(cfg_id: int) -> dict[str, Any]:
    with session() as s:
        cfg = s.get(RunConfig, cfg_id)
        if cfg is None:
            raise KeyError(cfg_id)
        out = []
        for r in s.query(Run).filter_by(run_config_id=cfg_id).order_by(Run.id).all():
            j = s.query(Judgment).filter_by(run_id=r.id).one_or_none()
            rr = s.query(RResult).filter_by(judgment_id=j.id).one_or_none() if j else None
            sols = (rr.r_output.get("solutions") or {}) if rr else {}
            out.append({
                "run_id": r.id, "arm": r.arm, "rep": r.rep_index, "status": r.status, "mechanical_id": r.mechanical_id,
                "attempts": len(r.attempts), "anchors": {n: b["anchors"] for n, b in
                                                          {**(j.decision["conditions"]), "outcome": j.decision["outcome"]}.items()} if j else None,
                "solutions": {k: _models(sols.get(k)) for k in ("complex", "parsimonious", "intermediate")} if rr else None,
            })
        return {"config": {"id": cfg.id, "model": cfg.model, "provider": cfg.provider, "template_version": cfg.template_version,
                           "reps": cfg.reps, "arms": cfg.arms, "project_id": cfg.project_id,
                           "role_approval": cfg.role_approval, "created_at": _iso(cfg.created_at)},
                "runs": out, "report": validation_report(s, cfg_id),
                "project": cfg.project_snapshot or project_summary(get_project(s, cfg.project_id))}


def _iso(dt: datetime) -> str:
    """Timestamps are stored as UTC; render one consistent ISO string with a Z suffix."""
    return dt.replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def rationales(cfg_id: int, arm: str | None = None, variable: str | None = None) -> list[dict[str, Any]]:
    out = []
    with session() as s:
        cfg0 = s.get(RunConfig, cfg_id)
        outcome_name = get_project(s, cfg0.project_id if cfg0 else "demo")["outcome"]
        for r in s.query(Run).filter_by(run_config_id=cfg_id).order_by(Run.id).all():
            if arm and r.arm != arm:
                continue
            j = s.query(Judgment).filter_by(run_id=r.id).one_or_none()
            if j is None:
                continue
            blocks = {**j.decision["conditions"], outcome_name: j.decision["outcome"]}
            for name, b in blocks.items():
                if variable and name != variable:
                    continue
                for k, why in b["rationale"].items():
                    out.append({"run_id": r.id, "arm": r.arm, "rep": r.rep_index, "variable": name, "anchor": k,
                                "value": b["anchors"][k], "rationale": why, "source": j.source, "attempt_id": j.attempt_id})
    return out


def attempt_detail(attempt_id: int) -> dict[str, Any]:
    from app.db.models import RunAttempt

    with session() as s:
        a = s.get(RunAttempt, attempt_id)
        if a is None:
            raise KeyError(attempt_id)
        return {"id": a.id, "run_id": a.run_id, "kind": a.attempt_kind, "provider": a.provider, "model_id": a.model_id,
                "prompt_sha256": a.prompt_sha256, "rendered_prompt": a.rendered_prompt, "raw_response": a.raw_response,
                "tokens_in": a.tokens_in, "tokens_out": a.tokens_out, "validation_ok": a.validation_ok,
                "validation_errors": a.validation_errors, "started_at": _iso(a.started_at)}


def owns(cfg_id: int, sid: str | None) -> bool:
    """A run is visible only to the browser that started it. Runs with no owner (local, older databases) are open."""
    with session() as s:
        cfg = s.get(RunConfig, cfg_id)
        return cfg is not None and (cfg.owner is None or cfg.owner == sid)


def attempt_owned(attempt_id: int, sid: str | None) -> bool:
    from app.db.models import RunAttempt

    with session() as s:
        a = s.get(RunAttempt, attempt_id)
        run = s.get(Run, a.run_id) if a else None
        return run is not None and owns(run.run_config_id, sid)


def purge_old(hours: int) -> int:
    """Deletes runs (and their attempts, judgments, results) older than `hours`, plus old role approvals."""
    from datetime import timedelta

    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=hours)
    n = 0
    with session() as s:
        for cfg in s.query(RunConfig).filter(RunConfig.created_at < cutoff).all():
            if BATCHES.get(cfg.id, {}).get("state") == "running":
                continue
            run_ids = [r.id for r in s.query(Run).filter_by(run_config_id=cfg.id).all()]
            if run_ids:
                jids = [j.id for j in s.query(Judgment).filter(Judgment.run_id.in_(run_ids)).all()]
                if jids:
                    s.query(RResult).filter(RResult.judgment_id.in_(jids)).delete(synchronize_session=False)
                s.query(Judgment).filter(Judgment.run_id.in_(run_ids)).delete(synchronize_session=False)
                s.query(CallLog).filter(CallLog.run_id.in_(run_ids)).delete(synchronize_session=False)
                from app.db.models import RunAttempt

                s.query(RunAttempt).filter(RunAttempt.run_id.in_(run_ids)).delete(synchronize_session=False)
                s.query(Run).filter(Run.id.in_(run_ids)).delete(synchronize_session=False)
            s.delete(cfg)
            BATCHES.pop(cfg.id, None)
            n += 1
        s.query(RoleApproval).filter(RoleApproval.approved_at < cutoff).delete(synchronize_session=False)
        s.commit()
    return n


def start_janitor(hours: int, every_seconds: int = 3600) -> None:
    import time

    def loop() -> None:
        while True:
            try:
                purge_old(hours)
            except Exception:  # never let cleanup take the app down
                pass
            time.sleep(every_seconds)

    threading.Thread(target=loop, daemon=True).start()
