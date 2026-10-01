"""Public-demo behaviour: visitor isolation, mode limits, retention."""

import time
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api import service
from app.db.models import RunConfig
from app.main import app

A = {"X-Session": "visitor-aaaaaaaaaaaa"}
B = {"X-Session": "visitor-bbbbbbbbbbbb"}
GEN = {"arms": {"roles": [], "generic": True, "mechanical": False}, "reps": 1}


@pytest.fixture
def demo(tmp_path, monkeypatch):
    monkeypatch.setenv("SA_QCA_MODE", "demo")
    monkeypatch.setenv("SA_QCA_MAX_CONCURRENT", "1")
    service.init_db(f"sqlite:///{tmp_path}/t.sqlite")
    service.BATCHES.clear()

    def slow_r(payload):
        time.sleep(0.4)
        return {"status": "ok", "solutions": {}, "versions": {"R": "fake", "QCA": "0", "jsonlite": "0"}}

    monkeypatch.setattr(service, "r_pipeline", slow_r)
    return TestClient(app)


def finish(c, rid, h):
    for _ in range(100):
        if c.get(f"/api/runs/{rid}/status", headers=h).json()["state"] != "running":
            return
        time.sleep(0.2)
    raise AssertionError("did not finish")


def test_mode_endpoint_and_headers(demo):
    m = demo.get("/api/mode").json()
    assert m["mode"] == "demo" and m["max_reps"] == 5
    r = demo.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["referrer-policy"] == "no-referrer"


def test_visitors_cannot_see_each_others_runs(demo):
    rid = demo.post("/api/runs", json=GEN, headers=A).json()["run_config_id"]
    finish(demo, rid, A)
    for path in ("status", "results", "dashboard", "rationales", "bundle", "report"):
        assert demo.get(f"/api/runs/{rid}/{path}", headers=A).status_code == 200, path
        assert demo.get(f"/api/runs/{rid}/{path}", headers=B).status_code == 404, path
    assert demo.post(f"/api/runs/{rid}/verify", headers=B).status_code == 404
    assert demo.post(f"/api/runs/{rid}/cancel", headers=B).status_code == 404
    assert demo.get(f"/api/runs/{rid}/events", headers=B).status_code == 404
    att = demo.get(f"/api/runs/{rid}/rationales", headers=A).json()
    aid = next(r["attempt_id"] for r in att if r["attempt_id"])
    assert demo.get(f"/api/attempts/{aid}", headers=A).status_code == 200
    assert demo.get(f"/api/attempts/{aid}", headers=B).status_code == 404
    # the session token may also arrive as a query parameter (EventSource, download links)
    assert demo.get(f"/api/runs/{rid}/report?sid={A['X-Session']}", headers={}).status_code == 200
    assert demo.get(f"/api/runs/{rid}/report").status_code == 404


def test_session_token_required_and_validated(demo):
    assert demo.post("/api/runs", json=GEN).status_code == 400
    assert demo.post("/api/runs", json=GEN, headers={"X-Session": "short"}).status_code == 400
    assert demo.post("/api/runs", json=GEN, headers={"X-Session": "bad token with spaces!!"}).status_code == 400


def test_uploads_and_other_projects_disabled(demo):
    assert demo.post("/api/projects/upload", files={"file": ("a.csv", b"a,b\n1,2\n")}, headers=A).status_code == 403
    assert demo.post("/api/projects/demo/configure", json={"variables": []}, headers=A).status_code == 403
    assert demo.get("/api/projects/demo/setup", headers=A).status_code == 403
    assert demo.get("/api/projects/p_whatever", headers=A).status_code == 403
    assert demo.get("/api/projects/demo", headers=A).status_code == 200
    body = {**GEN, "project_id": "p_whatever"}
    assert demo.post("/api/runs", json=body, headers=A).status_code == 403


def test_real_providers_and_large_runs_refused(demo):
    assert demo.post("/api/runs", json={**GEN, "provider": "anthropic", "model": "m"}, headers={**A, "X-Provider-Key": "k"}).status_code == 400
    assert demo.post("/api/runs", json={**GEN, "reps": 6}, headers=A).status_code == 400


def test_concurrency_limits(demo):
    rid = demo.post("/api/runs", json=GEN, headers=A).json()["run_config_id"]
    assert demo.post("/api/runs", json=GEN, headers=A).status_code == 429  # same visitor: one at a time
    assert demo.post("/api/runs", json=GEN, headers=B).status_code == 429  # global cap of 1 in this test
    finish(demo, rid, A)
    assert demo.post("/api/runs", json=GEN, headers=B).status_code == 200


def test_retention_purges_old_runs_but_not_running_ones(demo):
    rid = demo.post("/api/runs", json=GEN, headers=A).json()["run_config_id"]
    finish(demo, rid, A)
    with service.session() as s:
        s.get(RunConfig, rid).created_at = datetime.utcnow() - timedelta(hours=30)
        s.commit()
    assert service.purge_old(24) == 1
    assert demo.get(f"/api/runs/{rid}/status", headers=A).status_code == 404
    assert service.purge_old(24) == 0


def test_full_mode_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.delenv("SA_QCA_MODE", raising=False)
    service.init_db(f"sqlite:///{tmp_path}/t.sqlite")
    c = TestClient(app)
    assert c.get("/api/mode").json()["mode"] == "full"
    assert c.post("/api/projects/upload", files={"file": ("a.csv", b"a,b\n1,2\n3,4\n")}, headers=A).status_code == 200


def test_only_one_verification_at_a_time_on_the_demo(demo, monkeypatch):
    import app.main as main

    rid = demo.post("/api/runs", json=GEN, headers=A).json()["run_config_id"]
    finish(demo, rid, A)
    assert main._verify_lock.acquire(blocking=False)  # simulate a verification already in progress
    try:
        assert demo.post(f"/api/runs/{rid}/verify", headers=A).status_code == 429
    finally:
        main._verify_lock.release()


def test_verify_runs_in_the_background_and_is_private(demo):
    rid = demo.post("/api/runs", json=GEN, headers=A).json()["run_config_id"]
    finish(demo, rid, A)
    assert demo.get(f"/api/runs/{rid}/verify", headers=A).json() == {"state": "none"}
    assert demo.post(f"/api/runs/{rid}/verify", headers=A).status_code == 202
    assert demo.get(f"/api/runs/{rid}/verify", headers=B).status_code == 404
    for _ in range(100):
        st = demo.get(f"/api/runs/{rid}/verify", headers=A).json()
        if st["state"] == "done":
            break
        time.sleep(0.5)
    assert st["state"] == "done" and "ok" in st["result"]
