"""AI-assisted planning: validation, retry, logging, scripted fallback, privacy."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import assist
from app.api import service
from app.db.models import Base, HelperCall
from app.llm.base import ProviderError, RateLimitError
from app.llm.mock import MockProvider
from app.main import app

PHEN = "Hospitals in one region introducing an electronic triage tool during 2023; clinicians may or may not adopt it in daily practice. "
INPUTS = {"phenomenon": PHEN, "outcome": {"name": "USE_RATE", "description": "How consistently clinicians use the tool"}}


def stk(n=4, **over):
    items = [{"name": f"Group {i}", "description": "A group of people with first-hand knowledge of how the tool is used and what it costs them. " * 2,
              "relevance": "They see the work from a distinct angle."} for i in range(n)]
    items[0].update(over)
    return json.dumps({"stakeholders": items})


def cond(n=4, **over):
    items = [{"name": f"COND{i}", "definition": "What this condition means in the hospital setting.", "how_to_measure": "Survey scale from 1 to 7",
              "calibration": "direct", "direction": "positive", "rationale": "It may enable consistent use."} for i in range(n)]
    items[0].update(over)
    return json.dumps({"conditions": items})


@pytest.fixture
def session():
    e = create_engine("sqlite://")
    Base.metadata.create_all(e)
    with Session(e) as s:
        yield s


def run(session, kind, script, inputs=INPUTS, **kw):
    p = MockProvider(script)
    out = assist.run_helper(session, kind, inputs, p, "m", {}, "p_1", sleep=lambda s: None, **kw)
    return out, p


def test_valid_answer_is_returned_unedited_and_logged_with_its_prompt(session):
    out, p = run(session, "stakeholders", [stk()])
    assert out["ai_generated"] is True and out["provider"] == "mock" and len(out["items"]) == 4 and out["items"][0]["name"] == "Group 0"
    row = session.get(HelperCall, out["helper_call_ids"][0])
    assert row.kind == "stakeholders" and row.raw_response == stk() and row.validation_ok is True and PHEN.strip() in row.prompt
    assert row.model_id == "m" and row.project_id == "p_1"
    assert "USE_RATE" in p.prompts[0] and '"minItems": 3' in p.prompts[0]


def test_one_retry_with_the_errors_appended_then_success(session):
    out, p = run(session, "conditions", [cond(name="my cond"), cond()])
    assert out["ai_generated"] and len(p.prompts) == 2 and "previous answer was rejected" in p.prompts[1] and "pattern" in p.prompts[1].lower()
    rows = session.query(HelperCall).order_by(HelperCall.id).all()
    assert [r.attempt_kind for r in rows] == ["first", "validation_retry"] and [r.validation_ok for r in rows] == [False, True]


def test_two_failures_raise_and_both_are_logged_and_nothing_is_added(session):
    with pytest.raises(assist.HelperError, match="did not match the required format twice"):
        run(session, "stakeholders", [stk(n=1), "not json at all"])
    assert session.query(HelperCall).count() == 2 and all(r.validation_ok is False for r in session.query(HelperCall))


def test_strict_parsing_does_not_strip_code_fences(session):
    with pytest.raises(assist.HelperError):
        run(session, "stakeholders", ["```json\n" + stk() + "\n```", "```json\n" + stk() + "\n```"])


@pytest.mark.parametrize("script,fragment", [
    ([stk(name="Group 1"), stk(name="Group 1")], "unique"),
    ([cond(name="USE_RATE"), cond(name="USE_RATE")], "outcome"),
    ([cond(calibration="magic"), cond(calibration="magic")], "calibration"),
])
def test_semantic_checks(session, script, fragment):
    with pytest.raises(assist.HelperError) as e:
        run(session, "stakeholders" if "Group" in script[0] else "conditions", script)
    assert fragment in str(e.value).lower() or fragment in str(e.value)


def test_existing_names_are_not_repeated(session):
    inputs = {**INPUTS, "existing": [{"name": "Group 0", "description": "d"}]}
    with pytest.raises(assist.HelperError, match="already chosen"):
        run(session, "stakeholders", [stk(), stk()], inputs=inputs)


def test_rate_limits_are_retried_and_provider_errors_are_reported(session):
    out, _ = run(session, "stakeholders", [RateLimitError(), RateLimitError(), stk()])
    assert out["ai_generated"]
    with pytest.raises(assist.HelperError, match="rate-limiting"):
        run(session, "stakeholders", [RateLimitError()] * 6)
    with pytest.raises(assist.HelperError, match="workspace"):
        run(session, "stakeholders", [ProviderError("needs a workspace header")])


def test_inputs_are_checked_before_anything_is_sent(session):
    with pytest.raises(ValueError, match="describe the phenomenon"):
        assist.run_helper(session, "stakeholders", {"phenomenon": "short"}, MockProvider([stk()]), "m", {})
    with pytest.raises(ValueError):
        assist.check_inputs("magic", INPUTS)


def test_scripted_fallback_is_labelled_logged_and_generic_for_a_new_topic(session):
    out = assist.run_helper(session, "stakeholders", INPUTS, None, "m", {}, "p_1")
    assert out["provider"] == "scripted" and out["ai_generated"] is False and out["generic"] is True and "not tailored" in out["notice"]
    assert len(out["items"]) == 4 and all(len(i["description"]) >= 60 for i in out["items"])
    assert session.query(HelperCall).one().provider == "scripted"
    c = assist.run_helper(session, "conditions", INPUTS, None, "m", {})
    assert c["items"] == [] and "Enter your conditions yourself" in c["notice"]


def test_scripted_demo_suggestions_are_the_demo_studys_own(session):
    out = assist.run_helper(session, "conditions", {**INPUTS, "demo": True}, None, "m", {})
    assert [i["name"] for i in out["items"]] == ["TRUST", "SUPPORT", "RESOURCES"] and out["generic"] is False
    ok, errs, _ = assist.validate("conditions", json.dumps({"conditions": out["items"]}), INPUTS)
    assert ok, errs


# ---- API ----
@pytest.fixture
def client(tmp_path):
    service.init_db(f"sqlite:///{tmp_path}/t.sqlite")
    return TestClient(app, headers={"X-Session": "assist-test-visitor-1"})


def test_api_preview_shows_exactly_what_would_be_sent(client):
    body = {"inputs": INPUTS, "provider": "anthropic"}
    r = client.post("/api/assist/stakeholders/preview", json=body).json()
    assert r["scripted"] is False and PHEN.strip() in r["prompt"] and "never your data rows" in r["sent"]
    assert client.post("/api/assist/stakeholders/preview", json={"inputs": INPUTS, "provider": "scripted"}).json()["prompt"] is None
    assert client.post("/api/assist/stakeholders/preview", json={"inputs": {"phenomenon": "x"}}).status_code == 400
    assert client.post("/api/assist/nonsense/preview", json=body).status_code == 404


def test_api_anthropic_needs_a_key_and_uses_the_injected_provider(client, monkeypatch):
    assert client.post("/api/assist/stakeholders", json={"inputs": INPUTS, "provider": "anthropic"}).status_code == 400
    mock = MockProvider([stk()])
    monkeypatch.setattr(service, "make_helper_provider", lambda *a, **k: mock)
    r = client.post("/api/assist/stakeholders", json={"inputs": INPUTS, "provider": "anthropic", "project_id": "p_9"}, headers={"X-Provider-Key": "k"})
    assert r.status_code == 200 and r.json()["ai_generated"] is True and len(r.json()["items"]) == 4
    monkeypatch.setattr(service, "make_helper_provider", lambda *a, **k: MockProvider([ProviderError("boom")]))
    assert client.post("/api/assist/stakeholders", json={"inputs": INPUTS, "provider": "anthropic"}).status_code == 502


def test_api_demo_study_gets_its_own_scripted_suggestions(client):
    r = client.post("/api/assist/stakeholders", json={"inputs": INPUTS, "project_id": "demo"}).json()
    assert [i["name"] for i in r["items"]][0] == "Small-firm owner-manager" and r["ai_generated"] is False


def test_public_demo_never_calls_a_model_and_ignores_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("SA_QCA_MODE", "demo")
    service.init_db(f"sqlite:///{tmp_path}/d.sqlite")
    c = TestClient(app, headers={"X-Session": "assist-demo-visitor-1"})
    r = c.post("/api/assist/stakeholders", json={"inputs": INPUTS, "provider": "anthropic", "project_id": "demo"}, headers={"X-Provider-Key": "k"})
    assert r.status_code == 200 and r.json()["provider"] == "scripted"
    assert c.post("/api/assist/stakeholders", json={"inputs": INPUTS, "project_id": "p_other"}).status_code == 403
    assert c.post("/api/assist/stakeholders", json={"inputs": INPUTS}).status_code == 403
