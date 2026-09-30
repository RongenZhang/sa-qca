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

from app import rclient
from app.db.models import Base, Judgment, RoleApproval, RResult, Run, RunConfig
from app.demo import DemoProvider
from app.domain.mechanical import MechanicalConfig, generate_skaaning_configs
from app.domain.prompt import RoleSpec, load_default_template, prompt_hash
from app.engine.report import validation_report
from app.engine.rinput import build_r_input
from app.engine.runner import CostModel, EngineContext, run_batch
from app.llm.base import LLMProvider
from app.projects import get_project

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

    if "project_id" not in {c["name"] for c in inspect(_engine).get_columns("run_config")}:  # older dev databases
        with _engine.begin() as conn:
            conn.execute(text("ALTER TABLE run_config ADD COLUMN project_id VARCHAR DEFAULT 'demo'"))
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


def make_provider(kind: str, api_key: str | None, project: dict[str, Any]) -> LLMProvider:
    if kind == "demo-mock":
        return DemoProvider(project)
    if kind == "anthropic":
        if not api_key:
            raise ValueError("an API key is required for the Anthropic provider")
        from app.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key)
    raise ValueError(f"unknown provider {kind}")


def start_run(req: dict[str, Any], api_key: str | None) -> int:
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
    provider = make_provider(req["provider"], api_key, demo)
    template = load_default_template()
    prices = {}
    if req.get("price_in") is not None and req.get("price_out") is not None:
        prices = {req["model"]: (float(req["price_in"]), float(req["price_out"]))}
    sampling = {"temperature": req["temperature"]} if req.get("temperature") is not None else {}
    mech = generate_skaaning_configs(demo["data"], demo["reference"], demo["directions"], demo["outcome"],
                                     demo["reference_cutoffs"]) if arms.get("mechanical") else []
    ref_cfg = (MechanicalConfig("analyst_reference", "analyst's original specification", _reference_decision(demo), source="analyst")
               if demo["has_reference"] else None)
    with session() as s:
        cfg = RunConfig(
            project_id=req.get("project_id", "demo"), template_version="default_v1", template_sha256=prompt_hash(template), provider=provider.name,
            model=req["model"], sampling=sampling, reps=int(req["reps"]), tolerance=float(req.get("tolerance", 0.0)),
            spend_cap=req.get("spend_cap"), roles=[r.__dict__ for r in roles],
            arms=[*(f"role:{r.name}" for r in roles), *(["generic"] if arms.get("generic") else []),
                  *(["mechanical"] if arms.get("mechanical") else [])],
            mechanical_params={"generator": "skaaning_factorial", "shift_fraction": 0.05},
        )
        s.add(cfg)
        s.commit()
        cfg_id = cfg.id
    BATCHES[cfg_id] = {"state": "running", "cancel": False}

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
                BATCHES[cfg_id]["state"] = run_batch(s, ctx, c, roles, bool(arms.get("generic")), mech,
                                                     lambda: bool(BATCHES[cfg_id]["cancel"]), ref_cfg)
            except Exception as e:  # surface unexpected failures instead of hanging the UI
                BATCHES[cfg_id]["state"] = f"error: {e}"

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
        return {"state": BATCHES.get(cfg_id, {}).get("state", "unknown"), "total": len(runs),
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
                           "reps": cfg.reps, "arms": cfg.arms, "project_id": cfg.project_id, "created_at": _iso(cfg.created_at)},
                "runs": out, "report": validation_report(s, cfg_id)}


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
