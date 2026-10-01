"""Replication bundle (ZIP). Contains everything needed to re-run the QCA computation from the stored
judgments without any LLM call, plus the prompts and raw responses behind them. No API keys are ever
stored, and the builder refuses to write anything that looks like one."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import platform
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import CallLog, Judgment, RResult, Run, RunConfig
from app.domain.prompt import load_template, prompt_hash
from app.engine.report import validation_report

FORMAT_VERSION = 1
APP_VERSION = "0.5.0"
RSERVICE_R = Path(__file__).resolve().parents[3] / "rservice" / "R" / "pipeline.R"
KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]{20,}|x-api-key", re.I)


class BundleError(Exception):
    pass


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _j(x: Any) -> bytes:
    return (json.dumps(x, indent=2, ensure_ascii=False) + "\n").encode()


def _env_from_outputs(outs: list[dict[str, Any]]) -> dict[str, Any]:
    v: dict[str, Any] = next((o["versions"] for o in outs if o.get("versions")), {})
    return {"R": v.get("R"), "QCA": v.get("QCA"), "jsonlite": v.get("jsonlite")}


def build_files(session: Session, cfg_id: int) -> dict[str, bytes]:
    cfg = session.get(RunConfig, cfg_id)
    if cfg is None:
        raise BundleError("unknown run")
    runs = session.query(Run).filter_by(run_config_id=cfg_id).order_by(Run.id).all()
    files: dict[str, bytes] = {}

    # ---- analysis dataset (identical across runs; verified) ----
    r_results: dict[int, RResult] = {}
    judgments: dict[int, Judgment] = {}
    for r in runs:
        j = session.query(Judgment).filter_by(run_id=r.id).one_or_none()
        if j is None:
            continue
        judgments[r.id] = j
        rr = session.query(RResult).filter_by(judgment_id=j.id).one_or_none()
        if rr is not None:
            r_results[r.id] = rr
    if not r_results:
        raise BundleError("no completed computations to export yet")
    data = next(iter(r_results.values())).r_input["data"]
    for rr in r_results.values():
        if rr.r_input["data"] != data:
            raise BundleError("runs used different datasets; cannot bundle")
    files["data/analysis_data.json"] = json.dumps(data).encode()
    names = list(data)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(names)
    for row in zip(*(data[n] for n in names), strict=True):
        w.writerow([repr(float(x)) for x in row])
    files["data/analysis_data.csv"] = buf.getvalue().encode()

    # ---- project, roles, prompts ----
    snap = cfg.project_snapshot
    if snap is None:  # run predates snapshots: reconstruct from the project as it is now, and say so
        from app.projects import get_project, project_summary

        snap = {**project_summary(get_project(session, cfg.project_id)), "reconstructed_from_current_project": True}
    files["project/project.json"] = _j(snap)
    files["roles/approved_roles.json"] = _j({"approval": cfg.role_approval, "roles_used": cfg.roles})
    template = load_template(cfg.template_version)  # the exact template this run used
    files[f"prompts/template_{cfg.template_version}.j2"] = template.encode()
    template_ok = prompt_hash(template) == cfg.template_sha256

    # ---- attempts: rendered prompts + raw responses ----
    lines = []
    rl_total = 0
    for r in runs:
        for a in r.attempts:
            files[f"prompts/rendered/run{r.id:04d}_attempt{a.id:04d}_{a.attempt_kind}.txt"] = a.rendered_prompt.encode()
            rl_total += a.rate_limit_retries
            lines.append(json.dumps({
                "run_id": r.id, "arm": r.arm, "rep": r.rep_index, "attempt_id": a.id, "kind": a.attempt_kind,
                "provider": a.provider, "model_id": a.model_id, "sampling": a.sampling, "started_at": a.started_at.isoformat(),
                "prompt_sha256": a.prompt_sha256, "raw_response": a.raw_response, "tokens_in": a.tokens_in,
                "tokens_out": a.tokens_out, "est_cost": a.est_cost, "rate_limit_retries": a.rate_limit_retries,
                "validation_ok": a.validation_ok, "validation_errors": a.validation_errors}, ensure_ascii=False))
    files["llm/attempts.jsonl"] = ("\n".join(lines) + ("\n" if lines else "")).encode()
    calls = [{"run_id": c.run_id, "attempt_id": c.attempt_id, "kind": c.kind, "detail": c.detail, "at": c.at.isoformat()}
             for c in session.query(CallLog).join(Run, CallLog.run_id == Run.id).filter(Run.run_config_id == cfg_id).all()]
    files["llm/call_log.json"] = _j(calls)

    # ---- decisions, R inputs/outputs, run table ----
    spec_runs, table = [], []
    for r in runs:
        j = judgments.get(r.id)
        rr = r_results.get(r.id)
        if j:
            files[f"decisions/run{r.id:04d}.json"] = _j({"run_id": r.id, "arm": r.arm, "source": j.source,
                                                        "attempt_id": j.attempt_id, "decision": j.decision})
        if rr:
            files[f"replication/r_inputs/run{r.id:04d}.json"] = _j({k: v for k, v in rr.r_input.items() if k != "data"})
            files[f"results/r_outputs/run{r.id:04d}.json"] = _j(rr.r_output)
            spec_runs.append({"run_id": r.id, "arm": r.arm, "input_file": f"replication/r_inputs/run{r.id:04d}.json",
                              "expected_file": f"results/r_outputs/run{r.id:04d}.json"})
        table.append([r.id, r.arm, r.rep_index, r.mechanical_id or "", r.status, len(r.attempts)])
    tb = io.StringIO()
    tw = csv.writer(tb, lineterminator="\n")
    tw.writerow(["run_id", "source_id", "rep", "mechanical_id", "status", "attempts"])
    tw.writerows(table)
    files["results/runs.csv"] = tb.getvalue().encode()
    files["results/validation_report.json"] = _j(validation_report(session, cfg_id))

    outs = [rr.r_output for rr in r_results.values()]
    env = {**_env_from_outputs(outs), "python": sys.version.split()[0], "platform": platform.platform(), "app_version": APP_VERSION}
    files["environment/original_environment.json"] = _j(env)
    files["replication/spec.json"] = _j({"format": FORMAT_VERSION, "runs": spec_runs, "original_environment": env})
    files["replication/pipeline.R"] = RSERVICE_R.read_bytes()
    files["replication/replicate.R"] = (Path(__file__).parent / "replicate.R").read_bytes()
    files["README.md"] = _readme(cfg, len(runs), len(spec_runs), env).encode()

    # ---- safety: no credentials in any text file ----
    for path, content in files.items():
        if KEY_PATTERN.search(content.decode("utf-8", "ignore")):
            raise BundleError(f"refusing to export: {path} looks like it contains an API key")

    manifest = {
        "format": FORMAT_VERSION, "app_version": APP_VERSION, "run_config_id": cfg_id,
        "template": {"version": cfg.template_version, "sha256": cfg.template_sha256, "matches_bundled_file": template_ok},
        "provider": cfg.provider, "model": cfg.model, "n_runs": len(runs), "n_replicable_runs": len(spec_runs),
        "rate_limit_retries": rl_total,
        "files": [{"path": p, "sha256": _sha(c), "bytes": len(c)} for p, c in sorted(files.items())],
    }
    files["manifest.json"] = _j(manifest)
    return files


def _readme(cfg: RunConfig, n_runs: int, n_rep: int, env: dict[str, Any]) -> str:
    return f"""# SA-QCA replication bundle

Run #{cfg.id} · {cfg.provider}/{cfg.model} · prompt template {cfg.template_version} · {n_runs} runs ({n_rep} with a stored QCA computation)

## What is inside
- `data/` the analysis dataset exactly as sent to R (selected variables, after any listwise deletion the analyst chose)
- `project/project.json` the project as it stood when the run started: phenomenon description, variable definitions, instruments, original anchors and cutoffs
- `roles/approved_roles.json` the approved stakeholder roles and who approved them, when
- `prompts/` the prompt template and **every rendered prompt** (one file per attempt)
- `llm/attempts.jsonl` every attempt with the raw model response, model ID, sampling parameters, token use and validation result; `llm/call_log.json` rate-limit and provider events
- `decisions/` the judgments (anchors, cutoffs, rationales) handed to R, one per run, unedited
- `replication/` the R code and inputs; `results/` the solutions recorded at run time
- `manifest.json` SHA-256 checksum of every file

No API keys are stored anywhere in this bundle.

## Re-run the QCA computation (no LLM calls)
Requires R with `QCA` and `jsonlite` (original: {env.get('R')}, QCA {env.get('QCA')}).
```
Rscript replication/replicate.R
```
It re-runs calibration, truth table, necessity and minimization for every stored judgment and reports MATCH or MISMATCH against `results/r_outputs/`. Exit status 0 means every run reproduced exactly. The backend also offers `python -m app.exports.verify <bundle.zip>`, which checks the manifest checksums first.

## What is and is not reproducible
The QCA computation is deterministic and is reproduced exactly from the stored decisions. The model's answers are not regenerated: a provider may return different text on another day, so the stored raw responses are the record.
"""


def build_zip(session: Session, cfg_id: int) -> bytes:
    files = build_files(session, cfg_id)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(files):
            z.writestr(zipfile.ZipInfo(path, date_time=(2026, 1, 1, 0, 0, 0)), files[path], compress_type=zipfile.ZIP_DEFLATED)
    return out.getvalue()
