"""Pass-through conditions + breakpoint outcome, on the published Zhang & Ramesh (2024, ISJ) data (CC BY 4.0)."""

import io
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import service
from app.main import app

FIXTURE = Path(__file__).resolve().parents[3] / "rservice" / "tests" / "testthat" / "fixtures" / "zhang_ramesh_2024_isj.csv"
H = {"X-Session": "isj-test-visitor-0001"}
CONDS = ["ACC", "VISI", "AUTO", "INCEN1", "INCEN2"]
PUBLISHED = {"ACC*VISI*AUTO*~INCEN2", "ACC*AUTO*INCEN1*INCEN2", "VISI*AUTO*INCEN1*~INCEN2"}


@pytest.fixture
def client(tmp_path):
    service.init_db(f"sqlite:///{tmp_path}/t.sqlite")
    return TestClient(app, headers=H)


def cfg(**over):
    base = {"name": "ISJ", "case_description": "Fourteen blockchain platforms that adopted on-chain governance. " * 8, "drop_missing": False,
            "reference_cutoffs": {"consistency_threshold": 0.8, "frequency_threshold": 1, "pri_threshold": 0.75},
            "variables": [
                *[{"name": n, "role": "condition", "direction": "positive", "calibration": "precalibrated",
                   "construct_definition": f"{n} construct", "instrument": "four-value coding by two coders (0, 0.33, 0.67, 1)"} for n in CONDS],
                {"name": "Posts", "role": "outcome", "direction": "positive", "calibration": "breakpoints",
                 "construct_definition": "Generative governance engagement: how many governance proposals a platform's users produced",
                 "instrument": "Number of governance proposals", "breakpoints": {"break_0": 0, "break_33": 15, "break_67": 90}}]}
    base.update(over)
    return base


def upload(client):
    r = client.post("/api/projects/upload", files={"file": ("isj.csv", io.BytesIO(FIXTURE.read_bytes()), "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()["project_id"]


def test_validation_of_the_new_kinds(client):
    pid = upload(client)
    bad = cfg()
    bad["variables"][5]["calibration"] = "precalibrated"
    r = client.post(f"/api/projects/{pid}/configure", json=bad)
    assert r.status_code == 400 and "outcome must be calibrated by the agents" in r.json()["detail"]
    bad = cfg()
    bad["variables"][5]["breakpoints"] = {"break_0": 0, "break_33": 90, "break_67": 15}
    assert "not ordered" in client.post(f"/api/projects/{pid}/configure", json=bad).json()["detail"]
    bad = cfg()
    bad["variables"][0]["anchors"] = {"full_non_membership": 0, "crossover": 0.5, "full_membership": 1}
    assert "takes no anchors" in client.post(f"/api/projects/{pid}/configure", json=bad).json()["detail"]
    bad = cfg()
    bad["variables"][0]["name"] = "Posts"  # not a [0,1] column when used as already calibrated
    bad["variables"][5]["name"] = "ACC"
    bad["variables"][0]["calibration"] = "precalibrated"
    assert "between 0 and 1" in client.post(f"/api/projects/{pid}/configure", json=bad).json()["detail"]


def test_summary_and_prompt_for_the_published_design(client):
    pid = upload(client)
    p = client.post(f"/api/projects/{pid}/configure", json=cfg()).json()
    assert p["has_reference"] and [v["calibration"] for v in p["variables"]] == ["precalibrated"] * 5 + ["breakpoints"]
    assert p["reference"] == {"Posts": {"break_0": 0.0, "break_33": 15.0, "break_67": 90.0}}
    pr = client.post("/api/prompt/preview", json={"project_id": pid, "role": {"name": "Token holder", "description": "Votes with a stake."}}).json()["prompt"]
    assert pr.count("FIXED: this set is already calibrated") == 5 and pr.count("YOU CALIBRATE THIS SET WITH BREAKPOINTS") == 1
    schema = pr[pr.index('{\n  "$schema"'):]
    assert '"required": []' in schema and '"break_67"' in schema and "full_membership" in schema  # anchors def exists but is unused


@pytest.mark.skipif(shutil.which("Rscript") is None, reason="Rscript not available")
def test_reference_run_reproduces_the_published_solution_and_the_agents_set_breakpoints(client):
    pid = upload(client)
    client.post(f"/api/projects/{pid}/configure", json=cfg())
    ok = client.post("/api/roles/approve", json={"roles": [{"name": "Token holder", "description": "Votes with a stake."}], "approved_by": "t"}).json()
    body = {"project_id": pid, "role_set_hash": ok["roles_hash"], "reps": 2, "provider": "demo-mock",
            "arms": {"roles": ["Token holder"], "generic": True, "mechanical": True}}
    est = client.post("/api/runs/estimate", json=body).json()
    assert est["mechanical_runs"] == 5  # outcome breakpoints lower/higher + consistency 0.7/0.9 + frequency 2
    rid = client.post("/api/runs", json=body).json()["run_config_id"]
    t0 = time.time()
    while client.get(f"/api/runs/{rid}/status").json()["state"] == "running" and time.time() - t0 < 240:
        time.sleep(0.5)
    res = client.get(f"/api/runs/{rid}/results").json()
    ref = next(r for r in res["runs"] if r["arm"] == "reference")
    assert ref["status"] == "valid"
    assert {term for model in ref["solutions"]["complex"] for term in model} == PUBLISHED
    agent = [r for r in res["runs"] if r["arm"] in ("generic", "role:Token holder") and r["anchors"]]
    assert agent and all(set(r["anchors"]) == {"outcome"} for r in agent)            # nothing proposed for fixed conditions
    assert all(set(r["anchors"]["outcome"]) == {"break_0", "break_33", "break_67"} for r in agent)
    mech = [r for r in res["runs"] if r["arm"] == "mechanical"]
    assert len(mech) == 5 and all(r["status"] in ("valid", "valid_no_solution") for r in mech)
    # the exact prompt each agent saw marked the five conditions as fixed
    rats = client.get(f"/api/runs/{rid}/rationales?arm=generic").json()
    assert rats and all(r["variable"] == "Posts" for r in rats)
    att = client.get(f"/api/attempts/{next(r['attempt_id'] for r in rats if r['attempt_id'])}").json()
    assert att["rendered_prompt"].count("FIXED: this set is already calibrated") == 5
    # and the run is verifiable from a fresh R process
    assert client.post(f"/api/runs/{rid}/verify").status_code == 202
    for _ in range(120):
        v = client.get(f"/api/runs/{rid}/verify").json()
        if v["state"] == "done":
            break
        time.sleep(1)
    assert v["result"]["ok"], v


def test_cli_loads_a_project_from_files(tmp_path, monkeypatch, capsys):
    import json

    from app.cli import main

    monkeypatch.setenv("SA_QCA_DB", f"sqlite:///{tmp_path}/cli.sqlite")
    service._SessionLocal = None  # pick up the new database
    cfg_path = tmp_path / "project.json"
    cfg_path.write_text(json.dumps(cfg()))
    assert main(["load-project", "--csv", str(FIXTURE), "--config", str(cfg_path)]) == 0
    out = capsys.readouterr().out
    pid = out.split("Project ")[1].split(" ")[0]
    assert f"/?project={pid}" in out
    assert client_for_current_db().get(f"/api/projects/{pid}").json()["has_reference"] is True
    cfg_path.write_text(json.dumps({**cfg(), "variables": []}))
    assert main(["load-project", "--csv", str(FIXTURE), "--config", str(cfg_path)]) == 1
    assert "Could not load the project" in capsys.readouterr().out


def client_for_current_db():
    return TestClient(app, headers=H)
