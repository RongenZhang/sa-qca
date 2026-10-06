import copy
import io
import json
import shutil
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.api import service
from app.llm.base import ProviderError
from app.llm.mock import MockProvider
from app.main import app

pytestmark = pytest.mark.skipif(shutil.which("Rscript") is None, reason="Rscript not available")
H = {"X-Session": "interp-test-visitor-001"}
OTHER = {"X-Session": "interp-test-visitor-002"}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    service.init_db(f"sqlite:///{tmp_path_factory.mktemp('db')}/t.sqlite")
    c = TestClient(app, headers=H)
    roles = [{"name": r["name"], "description": r["description"]} for r in c.post("/api/roles/suggest").json()["roles"]]
    ok = c.post("/api/roles/approve", json={"roles": roles, "approved_by": "t"}).json()
    rid = c.post("/api/runs", json={"role_set_hash": ok["roles_hash"], "reps": 3, "arms": {"roles": [r["name"] for r in roles], "generic": True, "mechanical": True}}).json()["run_config_id"]
    t0 = time.time()
    while c.get(f"/api/runs/{rid}/status").json()["state"] == "running" and time.time() - t0 < 300:
        time.sleep(0.5)
    return c, rid


def good_narrative(facts):
    people = [s["label"] for s in facts["sources"] if s["kind"] == "stakeholder"]
    rob = [p["path"] for p in facts["paths"] if p["classification"] == "robust"]
    con = [p for p in facts["paths"] if p["classification"] != "robust" and p["in_analyst_solution"]]
    return {"headline": "Some findings hold under every reading and others depend on the reading used.",
            "robust_findings": [{"path": p, "meaning": "This path holds under every stakeholder reading, so it does not depend on whose bar is used."} for p in rob],
            "contested_findings": [{"path": p["path"], "holds_under": p["present_under"], "fails_under": p["absent_under"],
                                   "meaning": "This path is present under some readings and absent under others, which is consistent with a different bar."} for p in con],
            "stakeholder_perspectives": [{"stakeholder": n, "reading": "This stakeholder's reading produced the solution shown in the facts.", "implication": "Read it as one defensible view."} for n in people],
            "implications": "Report the robust findings as general and the contested ones together with the readings under which they hold.",
            "caveats": ["These are readings by scripted stand-ins, not evidence about real stakeholders."]}


def test_facts_and_rule_based_narrative_on_a_real_multi_stakeholder_run(built):
    c, rid = built
    r = c.get(f"/api/runs/{rid}/interpretation").json()
    f, n = r["facts"], r["narrative"]
    assert f["reference"]["solution"] == "RESOURCES*~TRUST + SUPPORT*TRUST" and f["agreement"]["n_stakeholders"] == 3
    paths = {p["path"]: p for p in f["paths"]}
    assert paths["SUPPORT*TRUST"]["classification"] == "robust"
    rest = paths["RESOURCES*~TRUST"]
    assert rest["classification"] == "contested" and rest["absent_under"] == ["Independent IT consultant"] and len(rest["present_under"]) == 2
    consultant = next(s for s in f["sources"] if s["label"] == "Independent IT consultant")
    assert {c["stance"] for c in consultant["calibration"]} == {"stricter"} and all(c["shift_pct_of_scale"] > 5 for c in consultant["calibration"])
    assert n["headline"].startswith("Of the 2 paths in the analyst's parsimonious solution, 1 holds under all 3 stakeholder readings and 1 depends")
    assert "scripted stand-in" in n["caveats"][0] and r["saved"] is None
    assert c.get(f"/api/runs/{rid}/interpretation?kind=complex").status_code == 200
    assert c.get(f"/api/runs/{rid}/interpretation?kind=bogus").status_code == 400


def test_scripted_ai_endpoint_returns_the_rule_based_narrative_and_logs_it(built):
    c, rid = built
    r = c.post(f"/api/runs/{rid}/interpretation/ai", json={}).json()
    assert r["ai_generated"] is False and r["provider"] == "scripted" and "fixed rules" in r["notice"]
    assert r["interpretation"] == c.get(f"/api/runs/{rid}/interpretation").json()["narrative"]


def test_model_drafted_narrative_must_be_grounded_in_the_facts(built, monkeypatch):
    c, rid = built
    real_make = service.make_helper_provider
    facts = c.get(f"/api/runs/{rid}/interpretation").json()["facts"]
    good = good_narrative(facts)
    monkeypatch.setattr(service, "make_helper_provider", lambda *a, **k: MockProvider([json.dumps(good)]))
    r = c.post(f"/api/runs/{rid}/interpretation/ai", json={"provider": "anthropic"}, headers={"X-Provider-Key": "k"})
    assert r.status_code == 200 and r.json()["ai_generated"] is True and r.json()["interpretation"] == good

    invented = copy.deepcopy(good)
    invented["robust_findings"].append({"path": "MAGIC*PATH", "meaning": "A finding that is not in the facts at all, so it must be rejected."})
    wrong_class = copy.deepcopy(good)
    wrong_class["robust_findings"] = [{"path": "RESOURCES*~TRUST", "meaning": "This path is contested in the facts, so calling it robust must be rejected."}]
    ghost = copy.deepcopy(good)
    ghost["stakeholder_perspectives"].append({"stakeholder": "A stakeholder nobody ran", "reading": "Invented reading that does not exist in the facts.", "implication": "Nothing follows from a stakeholder that was never run."})
    for bad, fragment in ((invented, "not a path in the facts"), (wrong_class, "not robust"), (ghost, "not a stakeholder in the facts")):
        monkeypatch.setattr(service, "make_helper_provider", lambda *a, _b=bad, **k: MockProvider([json.dumps(_b), json.dumps(_b)]))
        r = c.post(f"/api/runs/{rid}/interpretation/ai", json={"provider": "anthropic"}, headers={"X-Provider-Key": "k"})
        assert r.status_code == 502 and fragment in r.json()["detail"]
    p = MockProvider([json.dumps(invented), json.dumps(good)])
    monkeypatch.setattr(service, "make_helper_provider", lambda *a, **k: p)
    r = c.post(f"/api/runs/{rid}/interpretation/ai", json={"provider": "anthropic"}, headers={"X-Provider-Key": "k"})
    assert r.status_code == 200 and "not a path in the facts" in p.prompts[1] and "previous answer was rejected" in p.prompts[1]
    monkeypatch.setattr(service, "make_helper_provider", lambda *a, **k: MockProvider([ProviderError("boom")]))
    assert c.post(f"/api/runs/{rid}/interpretation/ai", json={"provider": "anthropic"}, headers={"X-Provider-Key": "k"}).status_code == 502
    monkeypatch.setattr(service, "make_helper_provider", real_make)
    assert c.post(f"/api/runs/{rid}/interpretation/ai", json={"provider": "anthropic"}).status_code == 400  # no key


def test_preview_shows_what_a_model_would_receive_and_never_data_rows(built):
    c, rid = built
    pr = c.post(f"/api/runs/{rid}/interpretation/preview", json={"provider": "anthropic"}).json()
    assert pr["scripted"] is False and "the ONLY results you may refer to" in pr["prompt"] and "SUPPORT*TRUST" in pr["prompt"] and "never your data rows" in pr["sent"]
    assert "H1," not in pr["prompt"]
    assert c.post(f"/api/runs/{rid}/interpretation/preview", json={"provider": "scripted"}).json()["prompt"] is None


def test_saving_the_researchers_version_and_exporting_it(built, monkeypatch):
    c, rid = built
    facts = c.get(f"/api/runs/{rid}/interpretation").json()["facts"]
    mine = good_narrative(facts)
    mine["headline"] = "My own headline for the stakeholder comparison of these solutions."
    assert c.put(f"/api/runs/{rid}/interpretation", json={"source": "bogus", "narrative": mine}).status_code == 400
    assert c.put(f"/api/runs/{rid}/interpretation", json={"source": "edited", "narrative": {"headline": "x"}}).status_code == 400
    assert c.put(f"/api/runs/{rid}/interpretation", json={"source": "edited", "kind": "bogus", "narrative": mine}).status_code == 400
    ok = c.put(f"/api/runs/{rid}/interpretation", json={"source": "edited", "narrative": mine, "notes": "Check this with practitioners."})
    assert ok.status_code == 200 and ok.json()["source"] == "edited"
    got = c.get(f"/api/runs/{rid}/interpretation").json()
    assert got["saved"]["narrative"]["headline"] == mine["headline"] and got["saved"]["notes"] == "Check this with practitioners."
    # exports carry it
    z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/runs/{rid}/bundle").content))
    doc = json.loads(z.read("interpretation/interpretation.json"))
    assert doc["saved_by_researcher"] is True and doc["source"] == "edited" and doc["narrative"]["headline"] == mine["headline"] and doc["facts"]["reference"]
    assert any(json.loads(line)["kind"] == "interpretation" for line in z.read("assist/helper_calls.jsonl").decode().splitlines())
    rep = c.get(f"/api/runs/{rid}/report").text
    assert "6. Interpretation from the stakeholder perspectives" in rep and mine["headline"] in rep and "Check this with practitioners." in rep
    assert "edited by the researcher" in rep and "7. AI-use statement" in rep
    assert "draft an interpretation" in rep  # a model-drafted attempt above was logged for this run, so the statement says so


def test_other_visitors_cannot_read_or_save_an_interpretation(built):
    c, rid = built
    o = TestClient(app, headers=OTHER)
    assert o.get(f"/api/runs/{rid}/interpretation").status_code == 404
    assert o.post(f"/api/runs/{rid}/interpretation/ai", json={}).status_code == 404
    assert o.put(f"/api/runs/{rid}/interpretation", json={"source": "rules", "narrative": {}}).status_code == 404
