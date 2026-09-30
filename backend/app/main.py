import asyncio
import json
from typing import Any

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api import service
from app.demo import SUGGESTED_ROLES
from app.domain.prompt import RoleSpec, case_description_warnings, load_default_template, prompt_warnings, render_prompt
from app.domain.schema import build_decision_schema
from app.projects import ProjectError, configure, create_upload, get_project, get_setup, project_summary

app = FastAPI(title="SA-QCA backend")
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
    anchors: dict[str, float | None] | None = None


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
async def upload(file: UploadFile = File(...)) -> dict[str, Any]:
    try:
        with service.session() as s:
            return create_upload(s, file.filename or "upload", await file.read())
    except ProjectError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/projects/{pid}/setup")
def project_setup(pid: str) -> dict[str, Any]:
    try:
        with service.session() as s:
            return get_setup(s, pid)
    except ProjectError as e:
        raise HTTPException(404 if "unknown" in str(e) else 400, str(e)) from e


@app.post("/api/projects/{pid}/configure")
def configure_project(pid: str, body: ConfigureIn) -> dict[str, Any]:
    cfg = body.model_dump()
    cfg["variables"] = [{**v, "anchors": v["anchors"] if v["anchors"] and any(x is not None for x in v["anchors"].values()) else None}
                        for v in cfg["variables"]]
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
    return {"prompt": prompt, "template_version": "default_v1",
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
        from app.domain.mechanical import generate_skaaning_configs

        if not d["has_reference"]:
            raise HTTPException(400, "the mechanical source needs the analyst's original anchors and cutoffs; add them in step 1")
        try:
            mech = len(generate_skaaning_configs(d["data"], d["reference"], d["directions"], d["outcome"], d["reference_cutoffs"]))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    out: dict[str, Any] = {"llm_calls_min": calls, "llm_calls_max": calls * 2, "mechanical_runs": mech,
                           "approx_input_tokens_per_call": tokens_in, "approx_output_tokens_per_call": 900,
                           "cost_usd_max": None}
    if body.price_in is not None and body.price_out is not None:
        out["cost_usd_max"] = calls * 2 * (tokens_in * body.price_in + 900 * body.price_out) / 1_000_000
    return out


@app.post("/api/runs")
def create_run(body: RunIn, x_provider_key: str | None = Header(default=None)) -> dict[str, Any]:
    try:
        return {"run_config_id": service.start_run(body.model_dump(), x_provider_key)}
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/runs/{cfg_id}/cancel")
def cancel(cfg_id: int) -> dict[str, str]:
    service.cancel_run(cfg_id)
    return {"status": "cancelling"}


@app.get("/api/runs/{cfg_id}/status")
def run_status(cfg_id: int) -> dict[str, Any]:
    return service.status(cfg_id)


@app.get("/api/runs/{cfg_id}/events")
async def events(cfg_id: int) -> StreamingResponse:
    async def gen() -> Any:
        while True:
            st = service.status(cfg_id)
            yield f"data: {json.dumps(st)}\n\n"
            if st["state"] != "running":
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/runs/{cfg_id}/results")
def run_results(cfg_id: int) -> dict[str, Any]:
    try:
        return service.results(cfg_id)
    except KeyError as e:
        raise HTTPException(404, "unknown run") from e


@app.get("/api/similarity/metrics")
def similarity_metrics() -> dict[str, str]:
    from app.domain.similarity import METRICS

    return {k: v[1] for k, v in METRICS.items()}


@app.get("/api/runs/{cfg_id}/dashboard")
def dashboard(cfg_id: int, kind: str = "parsimonious", metric: str = "jaccard_terms", policy: str = "union") -> dict[str, Any]:
    from app.domain.similarity import METRICS
    from app.engine.dashboard import build_dashboard

    if kind not in ("complex", "parsimonious", "intermediate") or metric not in METRICS or policy not in ("union", "first"):
        raise HTTPException(400, "bad kind, metric or policy")
    try:
        return build_dashboard(service.results(cfg_id), kind, metric, policy)
    except KeyError as e:
        raise HTTPException(404, "unknown run") from e


@app.get("/api/runs/{cfg_id}/rationales")
def rationales(cfg_id: int, arm: str | None = None, variable: str | None = None) -> list[dict[str, Any]]:
    return service.rationales(cfg_id, arm, variable)


@app.get("/api/attempts/{attempt_id}")
def attempt(attempt_id: int) -> dict[str, Any]:
    try:
        return service.attempt_detail(attempt_id)
    except KeyError as e:
        raise HTTPException(404, "unknown attempt") from e
