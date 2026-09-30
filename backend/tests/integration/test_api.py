import shutil
import time

import pytest
from fastapi.testclient import TestClient

from app.api import service
from app.main import app

pytestmark = pytest.mark.skipif(shutil.which("Rscript") is None, reason="Rscript not available")


@pytest.fixture
def client(tmp_path):
    service.init_db(f"sqlite:///{tmp_path}/t.sqlite")
    return TestClient(app)


def wait(client, rid, timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = client.get(f"/api/runs/{rid}/status").json()
        if st["state"] != "running":
            return st
        time.sleep(0.5)
    raise AssertionError("timeout")


def test_demo_endpoint(client):
    d = client.get("/api/demo").json()
    assert d["n_cases"] == 60 and d["warnings"] == [] and len(d["variables"]) == 4


def test_cannot_run_roles_before_approval(client):
    r = client.post("/api/runs", json={"arms": {"roles": ["A"], "generic": False, "mechanical": False}, "reps": 1})
    assert r.status_code == 403


def test_approval_validation(client):
    assert client.post("/api/roles/approve", json={"roles": [], "approved_by": "me"}).status_code == 400
    dup = {"name": "A", "description": "d"}
    assert client.post("/api/roles/approve", json={"roles": [dup, dup], "approved_by": "me"}).status_code == 400


def test_preview_role_vs_generic(client):
    g = client.post("/api/prompt/preview", json={}).json()["prompt"]
    r = client.post("/api/prompt/preview", json={"role": {"name": "Zed", "description": "zzz"}}).json()["prompt"]
    assert "Your vantage point" not in g and "Zed" in r


def test_anthropic_requires_key(client):
    ok = client.post("/api/roles/approve", json={"roles": [{"name": "A", "description": "d"}], "approved_by": "me"}).json()
    r = client.post("/api/runs", json={"role_set_hash": ok["roles_hash"], "provider": "anthropic", "model": "m",
                                        "arms": {"roles": ["A"], "generic": False, "mechanical": False}})
    assert r.status_code == 400


def test_full_demo_flow_with_mock_provider(client):
    roles = [{"name": "Vendor account manager", "description": "sells"},
             {"name": "Independent IT consultant", "description": "advises"}]
    ok = client.post("/api/roles/approve", json={"roles": roles, "approved_by": "tester"}).json()
    rid = client.post("/api/runs", json={
        "role_set_hash": ok["roles_hash"], "reps": 2,
        "arms": {"roles": [r["name"] for r in roles], "generic": True, "mechanical": False}}).json()["run_config_id"]
    st = wait(client, rid)
    assert st["state"] == "completed" and st["done"] == st["total"] == 6
    res = client.get(f"/api/runs/{rid}/results").json()
    assert {r["arm"] for r in res["runs"]} == {"role:Vendor account manager", "role:Independent IT consultant", "generic"}
    valid = [r for r in res["runs"] if r["status"] in ("valid", "valid_no_solution")]
    assert valid and all(r["anchors"] for r in valid)
    assert all(r["anchors"] is None for r in res["runs"] if r["status"] == "invalid")
    assert "invalid_rate" in res["report"]["generic"]
