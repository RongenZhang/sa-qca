"""Mock LLM -> validator -> REAL R pipeline on the demo project."""

import csv
import json
import shutil
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Base, Judgment, RResult, Run, RunConfig
from app.domain.prompt import RoleSpec, VariableSpec, load_default_template
from app.domain.stats import describe
from app.engine.rinput import build_r_input
from app.engine.runner import EngineContext, run_batch
from app.llm.mock import MockProvider
from app.rclient import run_pipeline_local

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.skipif(shutil.which("Rscript") is None, reason="Rscript not available")


def test_demo_project_end_to_end_and_deterministic():
    proj = json.loads((ROOT / "demo/project.json").read_text())
    rows = list(csv.DictReader((ROOT / "demo/dataset.csv").open()))
    data = {k: [float(r[k]) for r in rows] for k in rows[0] if k != "case"}
    variables = [
        VariableSpec(v["name"], v["role"], v["direction"], v["construct_definition"], v["instrument"],
                     v["units"], describe(data[v["name"]]))
        for v in proj["variables"]
    ]
    directions = {v["name"]: v["direction"] for v in proj["variables"]}
    dir_exp = {v["name"]: v.get("dir_exp") for v in proj["variables"]}
    ref = proj["reference_spec"]
    r = {k: "because" for k in ("full_non_membership", "crossover", "full_membership")}
    decision = {
        "conditions": {n: {"anchors": ref[n], "rationale": dict(r)} for n in ("TRUST", "SUPPORT", "RESOURCES")},
        "outcome": {"anchors": ref["ADOPTION"], "rationale": dict(r)},
        "truth_table": {**ref["truth_table"], "consistency_rationale": "c", "frequency_rationale": "f",
                        "pri_rationale": "p"},
    }
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        cfg = RunConfig(template_version="v1", template_sha256="x", provider="mock", model="m", reps=2)
        s.add(cfg); s.commit()
        ctx = EngineContext(
            MockProvider(lambda p: json.dumps(decision)), "m", {}, load_default_template(), variables, "cases", 0.0,
            lambda i: run_pipeline_local(i, str(ROOT / "rservice")),
            lambda d: build_r_input(d, data, directions, dir_exp, "ADOPTION"),
        )
        assert run_batch(s, ctx, cfg, [RoleSpec("Manager", "d")], False, []) == "completed"
        runs = s.query(Run).all()
        assert [x.status for x in runs] == ["valid", "valid"]
        outs = [s.query(RResult).join(Judgment).filter(Judgment.run_id == x.id).one().r_output for x in runs]
        assert outs[0] == outs[1]  # identical inputs -> identical solutions
        assert outs[0]["solutions"]["parsimonious"]["models"]
