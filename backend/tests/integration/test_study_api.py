"""The study plan: written before data exist, then data are attached and mapped to the plan."""

import io

import pytest
from fastapi.testclient import TestClient

from app.api import service
from app.main import app

H = {"X-Session": "study-test-visitor-01"}


@pytest.fixture
def client(tmp_path):
    service.init_db(f"sqlite:///{tmp_path}/t.sqlite")
    return TestClient(app, headers=H)


PLAN = {
    "phenomenon": "Mid-sized hospitals adopting an electronic triage tool during 2023, in one region. " * 6,
    "outcome": {"name": "USE_RATE", "description": "How consistently clinicians use the tool", "how_to_measure": "share of triage events using the tool",
                "calibration": "direct", "direction": "positive"},
    "stakeholders": [{"name": "Emergency nurses", "description": "Use the tool every shift.", "relevance": "Closest to the work", "ai": False}],
    "conditions": [
        {"name": "TRAINING", "definition": "Hours of training offered", "how_to_measure": "hours per clinician", "calibration": "direct", "direction": "positive", "ai": False},
        {"name": "Sponsor", "definition": "Visible executive sponsor", "how_to_measure": "coded 0 / 0.33 / 0.67 / 1", "calibration": "precalibrated", "direction": "positive", "ai": True},
        {"name": "GONE", "definition": "A condition with no column in the data", "how_to_measure": "", "calibration": "direct", "direction": "positive", "ai": False},
    ],
}
CSV = "hospital,training,SPONSOR,USE_RATE\n" + "\n".join(f"h{i},{4 + i % 9},{[0, 0.33, 0.67, 1][i % 4]},{(i * 7) % 100}" for i in range(30)) + "\n"


def draft(client):
    return client.post("/api/studies", json={"name": "Triage study"}).json()["project_id"]


def test_new_study_starts_empty_and_saves_the_plan(client):
    pid = draft(client)
    g = client.get(f"/api/projects/{pid}/study").json()
    assert g["study"]["phenomenon"] == "" and g["has_dataset"] is False and g["configured"] is False and g["name"] == "Triage study"
    r = client.put(f"/api/projects/{pid}/study", json={"study": PLAN, "name": "Hospital triage tool"})
    assert r.status_code == 200 and r.json()["name"] == "Hospital triage tool"
    again = client.get(f"/api/projects/{pid}/study").json()["study"]
    assert again["outcome"]["name"] == "USE_RATE" and [c["name"] for c in again["conditions"]] == ["TRAINING", "Sponsor", "GONE"]
    assert again["stakeholders"][0]["name"] == "Emergency nurses" and again["conditions"][1]["ai"] is True


def test_plan_validation_is_structural(client):
    pid = draft(client)

    def put(study):
        return client.put(f"/api/projects/{pid}/study", json={"study": study})

    bad = {**PLAN, "conditions": [{"name": "my condition", "calibration": "direct"}]}
    assert "QCA requirement" in put(bad).json()["detail"]
    bad = {**PLAN, "conditions": [{"name": "A"}, {"name": "a"}]}
    assert "unique names" in put(bad).json()["detail"]
    bad = {**PLAN, "conditions": [{"name": "A", "calibration": "magic"}]}
    assert "calibration must be one of" in put(bad).json()["detail"]
    bad = {**PLAN, "conditions": [{"name": f"C{i}"} for i in range(13)]}
    assert "at most 12 conditions" in put(bad).json()["detail"]
    assert "outcome" in put({**PLAN, "outcome": {"name": "bad name", "description": ""}}).json()["detail"]
    assert put({**PLAN, "phenomenon": "x" * 20_001}).status_code == 400
    assert client.put("/api/projects/nope/study", json={"study": PLAN}).status_code == 404


def test_attach_data_then_the_setup_is_drafted_from_the_plan(client):
    pid = draft(client)
    client.put(f"/api/projects/{pid}/study", json={"study": PLAN})
    assert client.get(f"/api/projects/{pid}/setup").status_code == 400  # no data yet
    up = client.post(f"/api/projects/{pid}/dataset", files={"file": ("d.csv", io.BytesIO(CSV.encode()), "text/csv")}).json()
    assert up["project_id"] == pid and up["n_rows"] == 30 and {c["name"] for c in up["columns"]} >= {"training", "SPONSOR", "USE_RATE"}
    s = client.get(f"/api/projects/{pid}/setup").json()
    assert s["config"] is None
    d = s["draft_config"]
    got = {v["name"]: v for v in d["variables"]}
    assert set(got) == {"training", "SPONSOR", "USE_RATE"}  # matched case-insensitively to TRAINING, Sponsor, USE_RATE
    assert got["training"]["role"] == "condition" and got["training"]["calibration"] == "direct" and got["training"]["construct_definition"] == "Hours of training offered"
    assert got["SPONSOR"]["calibration"] == "precalibrated" and got["SPONSOR"]["instrument"] == "coded 0 / 0.33 / 0.67 / 1"
    assert got["USE_RATE"]["role"] == "outcome"
    assert d["unmatched_plan"] == ["GONE"]  # planned but not in the file: the researcher is told
    assert "Outcome of interest: How consistently clinicians use the tool" in d["case_description"]


def test_a_new_file_keeps_the_plan_but_drops_an_old_setup(client):
    pid = draft(client)
    client.put(f"/api/projects/{pid}/study", json={"study": PLAN})
    client.post(f"/api/projects/{pid}/dataset", files={"file": ("d.csv", io.BytesIO(CSV.encode()), "text/csv")})
    cfg = {"name": "x", "case_description": "d", "drop_missing": False, "reference_cutoffs": None,
           "variables": [{"name": "training", "role": "condition", "direction": "positive", "construct_definition": "t", "instrument": "i"},
                         {"name": "SPONSOR", "role": "condition", "direction": "positive", "calibration": "precalibrated", "construct_definition": "s", "instrument": "i"},
                         {"name": "USE_RATE", "role": "outcome", "direction": "positive", "construct_definition": "u", "instrument": "i"}]}
    assert client.post(f"/api/projects/{pid}/configure", json=cfg).status_code == 200
    assert client.get(f"/api/projects/{pid}/setup").json()["config"] is not None
    client.post(f"/api/projects/{pid}/dataset", files={"file": ("d2.csv", io.BytesIO(CSV.encode()), "text/csv")})
    s = client.get(f"/api/projects/{pid}/setup").json()
    assert s["config"] is None and s["study"]["conditions"][0]["name"] == "TRAINING"
    assert client.post("/api/projects/nope/dataset", files={"file": ("d.csv", io.BytesIO(CSV.encode()), "text/csv")}).status_code == 404
    assert client.post(f"/api/projects/{pid}/dataset", files={"file": ("bad.pdf", io.BytesIO(b"x"), "application/pdf")}).status_code == 400


def test_demo_study_is_readable_but_not_editable(client):
    g = client.get("/api/projects/demo/study").json()
    assert g["read_only"] is True and g["study"]["outcome"]["name"] == "ADOPTION"
    assert [c["name"] for c in g["study"]["conditions"]] == ["TRUST", "SUPPORT", "RESOURCES"] and len(g["study"]["stakeholders"]) == 3
    assert client.put("/api/projects/demo/study", json={"study": PLAN}).status_code == 400


def test_public_demo_mode_blocks_new_studies(tmp_path, monkeypatch):
    monkeypatch.setenv("SA_QCA_MODE", "demo")
    service.init_db(f"sqlite:///{tmp_path}/d.sqlite")
    c = TestClient(app, headers=H)
    assert c.post("/api/studies", json={"name": "x"}).status_code == 403
    assert c.get("/api/projects/p_abc/study").status_code == 403
    assert c.get("/api/projects/demo/study").status_code == 200
    assert c.put("/api/projects/demo/study", json={"study": PLAN}).status_code == 403


def test_saved_studies_are_listed_newest_first_and_hidden_on_the_public_demo(client, tmp_path, monkeypatch):
    a = draft(client)
    client.put(f"/api/projects/{a}/study", json={"study": PLAN, "name": "First"})
    b = client.post("/api/studies", json={"name": "Second"}).json()["project_id"]
    listing = client.get("/api/studies").json()
    assert [s["name"] for s in listing][:2] == ["Second", "First"] and listing[1]["outcome"] == "USE_RATE" and listing[0]["id"] == b
    monkeypatch.setenv("SA_QCA_MODE", "demo")
    assert client.get("/api/studies").json() == []
