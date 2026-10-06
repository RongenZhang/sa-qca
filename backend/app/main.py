import asyncio
import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import assist, config
from app.api import service
from app.demo import SUGGESTED_ROLES
from app.domain.prompt import (
    DEFAULT_TEMPLATE_VERSION,
    RoleSpec,
    case_description_warnings,
    load_default_template,
    prompt_warnings,
    render_prompt,
)
from app.domain.schema import build_decision_schema
from app.projects import (
    ProjectError,
    attach_dataset,
    configure,
    create_draft,
    create_upload,
    get_project,
    get_setup,
    get_study,
    list_studies,
    project_summary,
    save_study,
)

app = FastAPI(title="SA-QCA backend")
SID_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


@app.middleware("http")
async def security_headers(request: Request, call_next: Any) -> Response:
    resp: Response = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"  # the session token may appear in a query string
    return resp


def get_sid(x_session: str | None = Header(default=None), sid: str | None = Query(default=None)) -> str | None:
    """Per-browser capability token (header, or query string for EventSource and download links)."""
    tok = x_session or sid
    if tok is not None and not SID_RE.match(tok):
        raise HTTPException(400, "bad session token")
    return tok


def owned_run(cfg_id: int, sid: str | None = Depends(get_sid)) -> int:
    if not service.owns(cfg_id, sid):
        raise HTTPException(404, "unknown run")  # same answer whether it is missing or someone else's
    return cfg_id


def not_on_demo() -> None:
    if config.demo_only():
        raise HTTPException(403, "uploads are disabled on this public demo; run the tool locally to use your own data")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


class RoleIn(BaseModel):
    name: str
    description: str
    relevance: str = ""


class ApproveIn(BaseModel):
    roles: list[RoleIn]
    approved_by: str


class PreviewIn(BaseModel):
    role: RoleIn | None = None
    project_id: str = "demo"


class VariableIn(BaseModel):
    name: str
    role: str
    direction: str = "positive"
    construct_definition: str = ""
    instrument: str = ""
    units: str = ""
    dir_exp: int | None = None
    calibration: str = "direct"  # direct | breakpoints | precalibrated
    anchors: dict[str, float | None] | None = None
    breakpoints: dict[str, float | None] | None = None


class ConfigureIn(BaseModel):
    name: str = ""
    case_description: str = ""
    variables: list[VariableIn]
    reference_cutoffs: dict[str, float | None] | None = None
    drop_missing: bool = False


class ArmsIn(BaseModel):
    roles: list[str] = []
    generic: bool = True
    mechanical: bool = True


class RunIn(BaseModel):
    project_id: str = "demo"
    role_set_hash: str = ""
    arms: ArmsIn
    reps: int = 3
    provider: str = "demo-mock"
    model: str = "demo-mock-1"
    temperature: float | None = None
    tolerance: float = 0.0
    spend_cap: float | None = None
    price_in: float | None = None
    price_out: float | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _project(pid: str) -> dict[str, Any]:
    if config.demo_only() and pid != "demo":
        raise HTTPException(403, "only the demo project is available on this public demo")
    try:
        with service.session() as s:
            return get_project(s, pid)
    except ProjectError as e:
        raise HTTPException(404 if "unknown" in str(e) else 400, str(e)) from e


@app.get("/api/demo")
def demo() -> dict[str, Any]:
    return project_summary(_project("demo"))


@app.get("/api/projects/{pid}")
def project(pid: str) -> dict[str, Any]:
    return project_summary(_project(pid))


@app.post("/api/projects/upload")
async def upload(file: UploadFile = File(...), _: None = Depends(not_on_demo)) -> dict[str, Any]:
    try:
        with service.session() as s:
            return create_upload(s, file.filename or "upload", await file.read())
    except ProjectError as e:
        raise HTTPException(400, str(e)) from e


class StudyIn(BaseModel):
    name: str | None = None
    study: dict[str, Any]


@app.get("/api/studies")
def studies() -> list[dict[str, Any]]:
    if config.demo_only():
        return []
    with service.session() as s:
        return list_studies(s)


@app.post("/api/studies")
def new_study(body: dict[str, Any], _: None = Depends(not_on_demo)) -> dict[str, Any]:
    """Starts a study from the researcher's own question; data are attached later."""
    with service.session() as s:
        return {"project_id": create_draft(s, str(body.get("name", "")))}


@app.get("/api/projects/{pid}/study")
def study(pid: str) -> dict[str, Any]:
    if config.demo_only() and pid != "demo":
        raise HTTPException(403, "only the demo study is available on this public demo")
    try:
        with service.session() as s:
            return get_study(s, pid)
    except ProjectError as e:
        raise HTTPException(404 if "unknown" in str(e) else 400, str(e)) from e


@app.put("/api/projects/{pid}/study")
def update_study(pid: str, body: StudyIn, _: None = Depends(not_on_demo)) -> dict[str, Any]:
    try:
        with service.session() as s:
            return save_study(s, pid, body.study, body.name)
    except ProjectError as e:
        raise HTTPException(404 if "unknown" in str(e) else 400, str(e)) from e


@app.post("/api/projects/{pid}/dataset")
async def project_dataset(pid: str, file: UploadFile = File(...), _: None = Depends(not_on_demo)) -> dict[str, Any]:
    try:
        with service.session() as s:
            return attach_dataset(s, pid, file.filename or "upload", await file.read())
    except ProjectError as e:
        raise HTTPException(404 if "unknown" in str(e) else 400, str(e)) from e


@app.get("/api/projects/{pid}/setup")
def project_setup(pid: str, _: None = Depends(not_on_demo)) -> dict[str, Any]:
    try:
        with service.session() as s:
            return get_setup(s, pid)
    except ProjectError as e:
        raise HTTPException(404 if "unknown" in str(e) else 400, str(e)) from e


@app.post("/api/projects/{pid}/configure")
def configure_project(pid: str, body: ConfigureIn, _: None = Depends(not_on_demo)) -> dict[str, Any]:
    cfg = body.model_dump()
    def given(d: dict[str, float | None] | None) -> dict[str, float | None] | None:
        return d if d and any(x is not None for x in d.values()) else None

    cfg["variables"] = [{**v, "anchors": given(v["anchors"]), "breakpoints": given(v["breakpoints"])} for v in cfg["variables"]]
    try:
        with service.session() as s:
            return configure(s, pid, cfg)
    except ProjectError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/roles/suggest")
def suggest_roles() -> dict[str, Any]:
    """Demo suggestions (scripted). Any LLM-generated suggestion is labelled and editable."""
    return {"ai_generated": True, "roles": SUGGESTED_ROLES}


@app.post("/api/roles/approve")
def approve(body: ApproveIn) -> dict[str, Any]:
    try:
        return service.approve_roles([r.model_dump() for r in body.roles], body.approved_by)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/prompt/preview")
def preview(body: PreviewIn) -> dict[str, Any]:
    d = _project(body.project_id)
    role = RoleSpec(body.role.name, body.role.description) if body.role else None
    prompt = render_prompt(load_default_template(), d["variables"], d["project"]["case_description"], role)
    return {"prompt": prompt, "template_version": DEFAULT_TEMPLATE_VERSION,
            "warnings": [*prompt_warnings(d["variables"]), *case_description_warnings(d["project"]["case_description"])],
            "sent_to_provider": "summary statistics and histogram bins only; no raw rows",
            "json_schema": build_decision_schema([v.name for v in d["variables"] if v.role == "condition"])}


@app.post("/api/runs/estimate")
def estimate(body: RunIn) -> dict[str, Any]:
    d = _project(body.project_id)
    n_agents = len(body.arms.roles) + (1 if body.arms.generic else 0)
    calls = n_agents * body.reps
    role = RoleSpec("x", "y")
    tokens_in = len(render_prompt(load_default_template(), d["variables"], "c", role)) // 4
    mech = 0
    if body.arms.mechanical:
        if not d["has_reference"]:
            raise HTTPException(400, "the mechanical source needs the analyst's original anchors and cutoffs; add them in step 1")
        try:
            mech = len(service.mechanical_configs(d))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    out: dict[str, Any] = {"llm_calls_min": calls, "llm_calls_max": calls * 2, "mechanical_runs": mech,
                           "approx_input_tokens_per_call": tokens_in, "approx_output_tokens_per_call": 900,
                           "cost_usd_max": None}
    if body.price_in is not None and body.price_out is not None:
        out["cost_usd_max"] = calls * 2 * (tokens_in * body.price_in + 900 * body.price_out) / 1_000_000
    return out


@app.post("/api/runs")
def create_run(body: RunIn, x_provider_key: str | None = Header(default=None),
               x_provider_workspace: str | None = Header(default=None),
               sid: str | None = Depends(get_sid)) -> dict[str, Any]:
    if sid is None:
        raise HTTPException(400, "missing session token")
    try:
        return {"run_config_id": service.start_run(body.model_dump(), x_provider_key, x_provider_workspace, sid)}
    except service.Busy as e:
        raise HTTPException(429, str(e)) from e
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/runs/{cfg_id}/cancel")
def cancel(cfg_id: int = Depends(owned_run)) -> dict[str, str]:
    service.cancel_run(cfg_id)
    return {"status": "cancelling"}


@app.get("/api/runs/{cfg_id}/status")
def run_status(cfg_id: int = Depends(owned_run)) -> dict[str, Any]:
    return service.status(cfg_id)


@app.get("/api/runs/{cfg_id}/events")
async def events(cfg_id: int = Depends(owned_run)) -> StreamingResponse:
    async def gen() -> Any:
        while True:
            st = service.status(cfg_id)
            yield f"data: {json.dumps(st)}\n\n"
            if st["state"] != "running":
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/runs/{cfg_id}/results")
def run_results(cfg_id: int = Depends(owned_run)) -> dict[str, Any]:
    try:
        return service.results(cfg_id)
    except KeyError as e:
        raise HTTPException(404, "unknown run") from e


class AssistIn(BaseModel):
    project_id: str | None = None
    inputs: dict[str, Any]
    provider: str = "scripted"
    model: str = "claude-opus-5-5"
    temperature: float | None = None


def _assist_inputs(kind: str, body: AssistIn) -> dict[str, Any]:
    inputs = dict(body.inputs)
    if body.project_id == "demo":
        inputs["demo"] = True
    elif config.demo_only():
        raise HTTPException(403, "only the demo study is available on this public demo")
    if kind not in assist.PLANNING:
        raise HTTPException(404, f"unknown helper {kind!r}")
    try:
        assist.check_inputs(kind, inputs)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return inputs


@app.post("/api/assist/{kind}/preview")
def assist_preview(kind: str, body: AssistIn) -> dict[str, Any]:
    """Shows exactly what would be sent to a model before anything is sent."""
    inputs = _assist_inputs(kind, body)
    scripted = config.demo_only() or body.provider in ("scripted", "demo-mock", "")
    return {"prompt": None if scripted else assist.build_prompt(kind, inputs), "scripted": scripted,
            "sent": "only the text you wrote above; never your data rows" if not scripted else "nothing: scripted suggestions are produced locally"}


@app.post("/api/assist/{kind}")
def assist_run(kind: str, body: AssistIn, x_provider_key: str | None = Header(default=None),
               x_provider_workspace: str | None = Header(default=None)) -> dict[str, Any]:
    inputs = _assist_inputs(kind, body)
    try:
        provider = service.make_helper_provider(body.provider, x_provider_key, x_provider_workspace)
        sampling = {"temperature": body.temperature} if body.temperature is not None else {}
        with service.session() as s:
            return assist.run_helper(s, kind, inputs, provider, body.model, sampling, body.project_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except assist.HelperError as e:
        raise HTTPException(502, str(e)) from e


class InterpIn(BaseModel):
    kind: str = "parsimonious"
    policy: str = "union"
    provider: str = "scripted"
    model: str = "claude-opus-5-5"
    temperature: float | None = None


class InterpSave(BaseModel):
    kind: str = "parsimonious"
    policy: str = "union"
    source: str  # rules | ai | edited
    narrative: dict[str, Any]
    notes: str = ""


def _interp_args(kind: str, policy: str) -> None:
    if kind not in ("complex", "parsimonious", "intermediate") or policy not in ("union", "first"):
        raise HTTPException(400, "bad kind or policy")


@app.get("/api/runs/{cfg_id}/interpretation")
def interpretation(cfg_id: int = Depends(owned_run), kind: str = "parsimonious", policy: str = "union") -> dict[str, Any]:
    from app.engine.interpret import template_narrative

    _interp_args(kind, policy)
    facts, _ = service.interpretation_context(cfg_id, kind, policy)
    return {"facts": facts, "narrative": template_narrative(facts), "saved": service.saved_interpretation(cfg_id)}


@app.post("/api/runs/{cfg_id}/interpretation/preview")
def interpretation_preview(body: InterpIn, cfg_id: int = Depends(owned_run)) -> dict[str, Any]:
    _interp_args(body.kind, body.policy)
    scripted = config.demo_only() or body.provider in ("scripted", "demo-mock", "")
    _, inputs = service.interpretation_context(cfg_id, body.kind, body.policy)
    return {"prompt": None if scripted else assist.build_prompt("interpretation", inputs), "scripted": scripted,
            "sent": "your study text and the computed facts of this run; never your data rows" if not scripted else "nothing: the rule-based summary is produced locally"}


@app.post("/api/runs/{cfg_id}/interpretation/ai")
def interpretation_ai(body: InterpIn, cfg_id: int = Depends(owned_run), x_provider_key: str | None = Header(default=None),
                      x_provider_workspace: str | None = Header(default=None)) -> dict[str, Any]:
    _interp_args(body.kind, body.policy)
    _, inputs = service.interpretation_context(cfg_id, body.kind, body.policy)
    try:
        provider = service.make_helper_provider(body.provider, x_provider_key, x_provider_workspace)
        sampling = {"temperature": body.temperature} if body.temperature is not None else {}
        with service.session() as s:
            return assist.run_helper(s, "interpretation", inputs, provider, body.model, sampling, None, run_config_id=cfg_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except assist.HelperError as e:
        raise HTTPException(502, str(e)) from e


@app.put("/api/runs/{cfg_id}/interpretation")
def save_interpretation(body: InterpSave, cfg_id: int = Depends(owned_run)) -> dict[str, Any]:
    from jsonschema import Draft202012Validator

    _interp_args(body.kind, body.policy)
    if body.source not in ("rules", "ai", "edited") or len(body.notes) > 20_000:
        raise HTTPException(400, "bad source or notes")
    errs = [e.message for e in Draft202012Validator(assist.SCHEMAS["interpretation"]).iter_errors(body.narrative)]
    if errs:
        raise HTTPException(400, "the narrative does not have the expected structure: " + "; ".join(errs[:3]))
    return service.save_interpretation(cfg_id, body.model_dump())


@app.get("/api/similarity/metrics")
def similarity_metrics() -> dict[str, str]:
    from app.domain.similarity import METRICS

    return {k: v[1] for k, v in METRICS.items()}


@app.get("/api/runs/{cfg_id}/dashboard")
def dashboard(cfg_id: int = Depends(owned_run), kind: str = "parsimonious", metric: str = "jaccard_terms", policy: str = "union") -> dict[str, Any]:
    from app.domain.similarity import METRICS
    from app.engine.dashboard import build_dashboard

    if kind not in ("complex", "parsimonious", "intermediate") or metric not in METRICS or policy not in ("union", "first"):
        raise HTTPException(400, "bad kind, metric or policy")
    try:
        return build_dashboard(service.results(cfg_id), kind, metric, policy)
    except KeyError as e:
        raise HTTPException(404, "unknown run") from e


@app.get("/api/runs/{cfg_id}/rationales")
def rationales(cfg_id: int = Depends(owned_run), arm: str | None = None, variable: str | None = None) -> list[dict[str, Any]]:
    return service.rationales(cfg_id, arm, variable)


@app.get("/api/attempts/{attempt_id}")
def attempt(attempt_id: int, sid: str | None = Depends(get_sid)) -> dict[str, Any]:
    if not service.attempt_owned(attempt_id, sid):
        raise HTTPException(404, "unknown attempt")
    try:
        return service.attempt_detail(attempt_id)
    except KeyError as e:
        raise HTTPException(404, "unknown attempt") from e


@app.get("/api/runs/{cfg_id}/bundle")
def bundle(cfg_id: int = Depends(owned_run)) -> Response:
    from app.exports.bundle import BundleError, build_zip

    try:
        with service.session() as s:
            data = build_zip(s, cfg_id)
    except BundleError as e:
        raise HTTPException(404 if "unknown" in str(e) else 400, str(e)) from e
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="sa-qca-run{cfg_id}-replication.zip"'})


_verify_lock = threading.Lock()


@app.post("/api/runs/{cfg_id}/verify", status_code=202)
def verify(cfg_id: int = Depends(owned_run)) -> dict[str, Any]:
    """Starts a background job: build the bundle for this run and re-run its replication script (can take minutes)."""
    from app.exports.bundle import BundleError, build_zip
    from app.exports.verify import verify_bundle

    if service.VERIFY_JOBS.get(cfg_id, {}).get("state") == "running":
        return {"state": "running"}
    # Verification starts another R process; on the memory-limited public demo only one may run at a time.
    if config.demo_only() and not _verify_lock.acquire(blocking=False):
        raise HTTPException(429, "another verification is in progress; please try again in a minute")
    service.VERIFY_JOBS[cfg_id] = {"state": "running"}

    def work() -> None:
        try:
            with service.session() as s:
                data = build_zip(s, cfg_id)
            service.VERIFY_JOBS[cfg_id] = {"state": "done", "result": verify_bundle(data)}
        except BundleError as e:
            service.VERIFY_JOBS[cfg_id] = {"state": "done", "result": {"ok": False, "error": str(e)}}
        except Exception as e:  # report instead of leaving the page waiting forever
            service.VERIFY_JOBS[cfg_id] = {"state": "done", "result": {"ok": False, "error": f"verification failed: {e}"}}
        finally:
            if config.demo_only() and _verify_lock.locked():
                _verify_lock.release()

    threading.Thread(target=work, daemon=True).start()
    return {"state": "running"}


@app.get("/api/runs/{cfg_id}/verify")
def verify_status(cfg_id: int = Depends(owned_run)) -> dict[str, Any]:
    return service.VERIFY_JOBS.get(cfg_id, {"state": "none"})


@app.get("/api/runs/{cfg_id}/report", response_class=HTMLResponse)
def report(cfg_id: int = Depends(owned_run)) -> HTMLResponse:
    from app.exports.report import build_report

    try:
        with service.session() as s:
            return HTMLResponse(build_report(s, cfg_id))
    except KeyError as e:
        raise HTTPException(404, "unknown run") from e


@app.get("/api/mode")
def mode() -> dict[str, Any]:
    return {"mode": "demo" if config.demo_only() else "full", "max_reps": config.max_reps(), "max_roles": config.max_roles(),
            "retention_hours": config.retention_hours()}


@app.on_event("startup")
def _startup() -> None:
    if config.demo_only():
        service.start_janitor(config.retention_hours())
    if os.environ.get("SA_QCA_R_WORKER", "1") != "0" and not os.environ.get("RSERVICE_URL"):
        threading.Thread(target=lambda: service.r_worker().warm(), daemon=True).start()  # hide R's start-up time


# Single-container deployment: serve the built frontend from the same origin (mounted last so /api wins).
_static = os.environ.get("SA_QCA_STATIC_DIR")
if _static and Path(_static).is_dir():
    app.mount("/", StaticFiles(directory=_static, html=True), name="static")
