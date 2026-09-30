import io
import shutil
import time

import pytest
from fastapi.testclient import TestClient

from app.api import service
from app.main import app
from app.projects import ProjectError, column_info, parse_upload, validate_config

CSV = "case,A,B,Y\n" + "\n".join(f"c{i},{1 + i % 7},{100 - i * 3},{(i * 13) % 101}" for i in range(40)) + "\n"


@pytest.fixture
def client(tmp_path):
    service.init_db(f"sqlite:///{tmp_path}/t.sqlite")
    return TestClient(app)


def upload(client, content=CSV, name="d.csv"):
    return client.post("/api/projects/upload", files={"file": (name, io.BytesIO(content.encode()), "text/csv")})


def cfg(**over):
    base = {"name": "P", "case_description": "cases", "drop_missing": False, "reference_cutoffs": None,
            "variables": [
                {"name": "A", "role": "condition", "direction": "positive", "construct_definition": "a", "instrument": "i"},
                {"name": "B", "role": "condition", "direction": "negative", "construct_definition": "b", "instrument": "i"},
                {"name": "Y", "role": "outcome", "direction": "positive", "construct_definition": "y", "instrument": "i"}]}
    base.update(over)
    return base


# ---- parsing ----
def test_parse_csv_semicolon_and_tab_and_bom():
    for text in ["a;b\n1;2\n3;4\n", "a\tb\n1\t2\n3\t4\n", "﻿a,b\n1,2\n3,4\n"]:
        h, r = parse_upload("x.csv", text.encode("utf-8"))
        assert h == ["a", "b"] and r == [["1", "2"], ["3", "4"]]


@pytest.mark.parametrize("content,err", [("a,b\n", "header row"), ("a,a\n1,2\n", "unique"), ("a,\n1,2\n", "header name")])
def test_parse_rejects_bad_files(content, err):
    with pytest.raises(ProjectError, match=err):
        parse_upload("x.csv", content.encode())


def test_parse_rejects_type_and_size():
    with pytest.raises(ProjectError):
        parse_upload("x.pdf", b"x")
    with pytest.raises(ProjectError, match="10 MB"):
        parse_upload("x.csv", b"a" * (10 * 1024 * 1024 + 1))


def test_xlsx_roundtrip():
    from openpyxl import Workbook

    wb = Workbook(); ws = wb.active
    ws.append(["A", "B"]); ws.append([1, 2.5]); ws.append([3, None])
    buf = io.BytesIO(); wb.save(buf)
    h, r = parse_upload("x.xlsx", buf.getvalue())
    assert h == ["A", "B"] and r == [["1", "2.5"], ["3", None]]


def test_column_info_numeric_and_missing():
    info = {c["name"]: c for c in column_info(["n", "t"], [["1", "x"], [None, "y"], ["3", "z"]])}
    assert info["n"]["numeric"] and info["n"]["n_missing"] == 1 and not info["t"]["numeric"]
    thousands = column_info(["v"], [["1,234"], ["2,000"]])
    assert thousands[0]["numeric"]


# ---- validation ----
def info3():
    return {n: {"numeric": True, "n_missing": 0, "n_unique": 10} for n in "ABY"}


def test_validate_config_problems():
    base = cfg()
    assert validate_config(base, info3(), 40) == []
    bad = cfg(variables=[{**v, "role": "condition"} for v in base["variables"]])
    assert any("exactly one outcome" in e for e in validate_config(bad, info3(), 40))
    one = cfg(variables=base["variables"][1:])
    assert any("at least two conditions" in e for e in validate_config(one, info3(), 40))
    i = info3(); i["A"]["numeric"] = False; i["B"]["n_missing"] = 2
    errs = " ".join(validate_config(base, i, 40))
    assert "not numeric" in errs and "missing values" in errs
    assert validate_config({**base, "drop_missing": True}, {**info3(), "B": {**info3()["B"], "n_missing": 2}}, 40) == []
    badname = cfg(variables=[{**base["variables"][0], "name": "my var"}, *base["variables"][1:]])
    assert any("QCA variable names" in e for e in validate_config(badname, {**info3(), "my var": info3()["A"]}, 40))


def test_validate_reference_anchor_ordering_by_direction():
    v = cfg()["variables"]
    v[0]["anchors"] = {"full_non_membership": 6, "crossover": 4, "full_membership": 2}
    assert any("not ordered" in e for e in validate_config(cfg(variables=v), info3(), 40))
    v[0]["anchors"] = {"full_non_membership": 2, "crossover": 4}
    assert any("all three" in e for e in validate_config(cfg(variables=v), info3(), 40))
    v[0]["anchors"] = {"full_non_membership": 2, "crossover": 4, "full_membership": 6}
    v[1]["anchors"] = {"full_non_membership": 90, "crossover": 50, "full_membership": 10}
    assert validate_config(cfg(variables=v), info3(), 40) == []


# ---- API ----
def test_upload_configure_and_project(client):
    up = upload(client).json()
    assert up["n_rows"] == 40 and {c["name"] for c in up["columns"]} == {"case", "A", "B", "Y"}
    assert client.get(f"/api/projects/{up['project_id']}").status_code == 400  # not configured yet
    r = client.post(f"/api/projects/{up['project_id']}/configure", json=cfg())
    assert r.status_code == 200
    p = r.json()
    assert p["n_cases"] == 40 and not p["has_reference"] and not p["is_demo"]
    assert {v["name"] for v in p["variables"]} == {"A", "B", "Y"} and p["variables"][0]["stats"]["n"] == 40
    assert client.get("/api/projects/nope").status_code == 404


def test_configure_rejects_and_drops_missing(client):
    csv_missing = CSV.replace("c3,4,91,39", "c3,4,,39")
    pid = upload(client, csv_missing).json()["project_id"]
    assert client.post(f"/api/projects/{pid}/configure", json=cfg()).status_code == 400
    ok = client.post(f"/api/projects/{pid}/configure", json=cfg(drop_missing=True)).json()
    assert ok["n_cases"] == 39 and ok["n_dropped"] == 1


def test_mechanical_requires_reference(client):
    pid = upload(client).json()["project_id"]
    client.post(f"/api/projects/{pid}/configure", json=cfg())
    body = {"project_id": pid, "arms": {"roles": [], "generic": True, "mechanical": True}, "reps": 1}
    assert client.post("/api/runs/estimate", json=body).status_code == 400
    assert client.post("/api/runs", json=body).status_code == 400


def test_preview_uses_uploaded_project(client):
    pid = upload(client).json()["project_id"]
    client.post(f"/api/projects/{pid}/configure", json=cfg(case_description="UNIQUE CASE TEXT"))
    pr = client.post("/api/prompt/preview", json={"project_id": pid}).json()["prompt"]
    assert "UNIQUE CASE TEXT" in pr and "TRUST" not in pr and "### B" in pr and "negative orientation" in pr


@pytest.mark.skipif(shutil.which("Rscript") is None, reason="Rscript not available")
def test_full_flow_on_uploaded_data_with_reference_and_negative_variable(client):
    pid = upload(client).json()["project_id"]
    v = cfg()["variables"]
    v[0]["anchors"] = {"full_non_membership": 2, "crossover": 4, "full_membership": 6}
    v[1]["anchors"] = {"full_non_membership": 90, "crossover": 50, "full_membership": 10}
    v[2]["anchors"] = {"full_non_membership": 20, "crossover": 50, "full_membership": 80}
    p = client.post(f"/api/projects/{pid}/configure", json=cfg(variables=v, reference_cutoffs={
        "consistency_threshold": 0.7, "frequency_threshold": 1, "pri_threshold": None})).json()
    assert p["has_reference"]
    ok = client.post("/api/roles/approve", json={"roles": [{"name": "Analyst X", "description": "d"}], "approved_by": "t"}).json()
    rid = client.post("/api/runs", json={"project_id": pid, "role_set_hash": ok["roles_hash"], "reps": 2,
                                         "arms": {"roles": ["Analyst X"], "generic": True, "mechanical": False}}).json()["run_config_id"]
    t0 = time.time()
    while time.time() - t0 < 240:
        st = client.get(f"/api/runs/{rid}/status").json()
        if st["state"] != "running":
            break
        time.sleep(0.5)
    assert st["state"] == "completed" and st["done"] == st["total"] == 5
    res = client.get(f"/api/runs/{rid}/results").json()
    assert res["config"]["project_id"] == pid
    agent_ok = [r for r in res["runs"] if r["arm"] != "reference" and r["anchors"]]
    assert agent_ok and all(r["anchors"]["B"]["full_non_membership"] > r["anchors"]["B"]["full_membership"] for r in agent_ok)
    d = client.get(f"/api/runs/{rid}/dashboard").json()
    assert "reference" not in d["arms"] and set(d["arms"]) == {"role:Analyst X", "generic"}
    ref = next(r for r in res["runs"] if r["arm"] == "reference")
    assert ref["status"] in ("valid", "valid_no_solution") and ref["anchors"]["B"]["full_non_membership"] == 90
    assert client.get(f"/api/runs/{rid}/rationales?variable=Y").json()


def test_setup_returns_config_and_demo_not_editable(client):
    pid = upload(client).json()["project_id"]
    client.post(f"/api/projects/{pid}/configure", json=cfg(case_description="first version"))
    s = client.get(f"/api/projects/{pid}/setup").json()
    assert s["upload"]["n_rows"] == 40 and s["config"]["case_description"] == "first version"
    assert {v["name"] for v in s["config"]["variables"]} == {"A", "B", "Y"}
    assert client.get("/api/projects/demo/setup").status_code == 400
    assert client.get("/api/projects/nope/setup").status_code == 404


def test_edit_changes_future_prompts_but_past_runs_keep_their_snapshot(client):
    pid = upload(client).json()["project_id"]
    client.post(f"/api/projects/{pid}/configure", json=cfg(case_description="ORIGINAL TEXT " * 40))
    body = {"project_id": pid, "reps": 1, "arms": {"roles": [], "generic": True, "mechanical": False}}
    rid = client.post("/api/runs", json=body).json()["run_config_id"]
    t0 = time.time()
    while client.get(f"/api/runs/{rid}/status").json()["state"] == "running" and time.time() - t0 < 120:
        time.sleep(0.3)
    client.post(f"/api/projects/{pid}/configure", json=cfg(case_description="REVISED TEXT " * 40))
    assert "REVISED TEXT" in client.post("/api/prompt/preview", json={"project_id": pid}).json()["prompt"]
    res = client.get(f"/api/runs/{rid}/results").json()
    assert res["project"]["case_description"].startswith("ORIGINAL TEXT")
    assert res["project"]["dataset_sha256"]
    att = client.get(f"/api/runs/{rid}/rationales").json()
    agent = next((r for r in att if r["source"] == "agent"), None)
    if agent:
        assert "ORIGINAL TEXT" in client.get(f"/api/attempts/{agent['attempt_id']}").json()["rendered_prompt"]
