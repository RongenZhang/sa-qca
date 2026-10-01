import io
import json
import re
import shutil
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.api import service
from app.exports.verify import verify_bundle
from app.main import app

pytestmark = pytest.mark.skipif(shutil.which("Rscript") is None, reason="Rscript not available")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    service.init_db(f"sqlite:///{tmp_path_factory.mktemp('db')}/t.sqlite")
    c = TestClient(app, headers={"X-Session": "test-visitor-0001"})
    ok = c.post("/api/roles/approve", json={"roles": [{"name": "Vendor account manager", "description": "sells"}], "approved_by": "t"}).json()
    rid = c.post("/api/runs", json={"role_set_hash": ok["roles_hash"], "reps": 3,
                                    "arms": {"roles": ["Vendor account manager"], "generic": True, "mechanical": False}}).json()["run_config_id"]
    t0 = time.time()
    while c.get(f"/api/runs/{rid}/status").json()["state"] == "running" and time.time() - t0 < 240:
        time.sleep(0.5)
    r = c.get(f"/api/runs/{rid}/bundle")
    assert r.status_code == 200
    return c, rid, r.content


def names(z):
    return set(zipfile.ZipFile(io.BytesIO(z)).namelist())


def test_bundle_contents_and_manifest(built):
    c, rid, z = built
    zf = zipfile.ZipFile(io.BytesIO(z))
    n = names(z)
    for must in ("README.md", "manifest.json", "data/analysis_data.json", "data/analysis_data.csv", "project/project.json",
                 "roles/approved_roles.json", "llm/attempts.jsonl", "replication/replicate.R", "replication/pipeline.R",
                 "replication/spec.json", "results/runs.csv", "results/validation_report.json", "environment/original_environment.json"):
        assert must in n, must
    manifest = json.loads(zf.read("manifest.json"))
    assert {f["path"] for f in manifest["files"]} == n - {"manifest.json"}
    assert manifest["template"]["matches_bundled_file"] is True
    attempts = [json.loads(line) for line in zf.read("llm/attempts.jsonl").decode().splitlines()]
    rendered = [p for p in n if p.startswith("prompts/rendered/")]
    assert len(rendered) == len(attempts) > 0  # every attempt's exact prompt is archived
    assert all(a["raw_response"] is not None and a["model_id"] for a in attempts)
    decisions = [p for p in n if p.startswith("decisions/")]
    assert decisions and all(json.loads(zf.read(p))["decision"]["outcome"] for p in decisions)
    assert json.loads(zf.read("roles/approved_roles.json"))["approval"]["approved_by"] == "t"
    assert json.loads(zf.read("project/project.json"))["case_description"]


def test_no_credentials_anywhere(built):
    _, _, z = built
    zf = zipfile.ZipFile(io.BytesIO(z))
    for name in zf.namelist():
        assert not re.search(r"sk-[A-Za-z0-9_\-]{20,}", zf.read(name).decode("utf-8", "ignore")), name


def test_verify_reproduces_every_run(built):
    _, _, z = built
    res = verify_bundle(z)
    assert res["ok"], res
    assert res["manifest_ok"] and res["n_match"] == res["n_runs"] > 0 and res["n_mismatch"] == 0


def test_verify_detects_tampered_result(built):
    _, _, z = built
    src = zipfile.ZipFile(io.BytesIO(z))
    victim = next(p for p in src.namelist() if p.startswith("results/r_outputs/"))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == victim:
                o = json.loads(data)
                o["solutions"]["complex"]["models"] = [{"terms": [{"expression": "TAMPERED", "literals": [], "inclS": 1, "PRI": 1, "covS": 1}], "solution_fit": None}]
                data = json.dumps(o).encode()
            dst.writestr(name, data)
    res = verify_bundle(out.getvalue())
    assert not res["ok"] and "checksum differs" in " ".join(res["manifest_problems"])  # caught by the manifest
    # and if the manifest is also rewritten to match, the replication itself catches it
    z2 = zipfile.ZipFile(io.BytesIO(out.getvalue()))
    m = json.loads(z2.read("manifest.json"))
    import hashlib
    for f in m["files"]:
        if f["path"] == victim:
            f["sha256"] = hashlib.sha256(z2.read(victim)).hexdigest()
    out2 = io.BytesIO()
    with zipfile.ZipFile(out2, "w") as dst:
        for name in z2.namelist():
            dst.writestr(name, json.dumps(m).encode() if name == "manifest.json" else z2.read(name))
    res2 = verify_bundle(out2.getvalue())
    assert not res2["ok"] and res2["n_mismatch"] == 1 and res2["manifest_ok"]


def test_verify_rejects_garbage_and_unsafe_paths():
    assert not verify_bundle(b"not a zip")["ok"]
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("../evil.txt", "x")
    assert "unsafe" in verify_bundle(out.getvalue())["error"]


def test_bundle_unknown_run_is_404(built):
    c, _, _ = built
    assert c.get("/api/runs/99999/bundle").status_code in (404, 400)


def test_report_contents_and_ai_statement(built):
    c, rid, _ = built
    r = c.get(f"/api/runs/{rid}/report")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    t = r.text
    for must in ("candidate protocol for discussion", "Anchor sources", "demo-mock-1", "AI-use statement", "Vendor account manager",
                 "never edited", "exactly one further attempt", "Analyst's original", "Invalid rate", "<svg"):
        assert must in t, must
    assert "TRUST" in t and "Managerial trust" in t
    assert re.search(r"\d+ of \d+ agent runs", t)
    assert c.get("/api/runs/99999/report").status_code == 404


def test_report_warns_when_run_used_scripted_responses(built):
    c, rid, _ = built
    t = c.get(f"/api/runs/{rid}/report").text
    assert "Scripted test run" in t and "Do not use this statement" in t
    assert "R R version" not in t and "between 2026" not in t or " and " in t
