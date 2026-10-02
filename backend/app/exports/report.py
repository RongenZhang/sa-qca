"""Self-contained HTML report (print it to PDF from the browser). Every figure comes from stored runs."""

from __future__ import annotations

import html
from collections import Counter
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import CallLog, Run, RunAttempt, RunConfig
from app.engine.dashboard import build_dashboard

E = html.escape


def source_label(arm: str) -> str:
    return (f"Stakeholder: {arm[5:]}" if arm.startswith("role:") else
            {"generic": "Generic", "mechanical": "Mechanical", "reference": "Analyst's original"}.get(arm, arm))


def _table(head: list[str], rows: list[list[Any]]) -> str:
    th = "".join(f"<th>{E(str(h))}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{E(str(c))}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>"


def _sim_svg(d: dict[str, Any]) -> str:
    arms = d["arms"]
    if not d["similarity"] or not arms:
        return "<p>No reference solution, so no similarity scores.</p>"
    W, H, L, T, B = 640, 300, 50, 14, 70
    cw = (W - L - 10) / len(arms)

    def y(v: float) -> float:
        return T + (1 - v) * (H - T - B)

    pal = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#F0E442"]
    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Similarity to the analyst solution by source" font-family="sans-serif" font-size="11">',
           f'<rect width="{W}" height="{H}" fill="#fff"/>']
    for t, lab in ((0, "nothing in common"), (0.5, ""), (1, "same solution")):
        out.append(f'<line x1="{L}" x2="{W - 8}" y1="{y(t)}" y2="{y(t)}" stroke="#d9dde1"/><text x="{L - 6}" y="{y(t) + 4}" text-anchor="end">{t}</text>')
        if lab:
            out.append(f'<text x="{W - 10}" y="{y(t) - 4}" text-anchor="end" fill="#5b6670" font-size="10">{lab}</text>')
    ci = 0
    for i, a in enumerate(arms):
        col = "#555" if a == "generic" else "#999" if a == "mechanical" else pal[ci % len(pal)]
        ci += a.startswith("role:")
        cx = L + cw * (i + 0.5)
        groups = Counter(round(s["score"], 6) for s in d["similarity"] if s["arm"] == a)
        for score, n in groups.items():
            r = 7 + min(10, n ** 0.5 * 2.5)
            out.append(f'<circle cx="{cx}" cy="{y(score)}" r="{r}" fill="{col}" fill-opacity=".85" stroke="#fff"/>'
                       f'<text x="{cx}" y="{y(score) + 4}" text-anchor="middle" fill="#fff" font-weight="700">{n}</text>')
        label = source_label(a)
        out.append(f'<text x="{cx}" y="{H - B + 16}" text-anchor="middle">{E(label[:22])}</text>'
                   f'<text x="{cx}" y="{H - B + 30}" text-anchor="middle" fill="#5b6670">{d["valid_runs"].get(a, 0)} runs, {d["distinct_solutions"].get(a, 0)} distinct</text>')
    out.append("</svg>")
    return "".join(out)


def ai_use_statement(cfg: RunConfig, runs: list[Run], attempts: list[RunAttempt], env: dict[str, Any], rl: int) -> str:
    agent = [r for r in runs if r.arm.startswith("role:") or r.arm == "generic"]
    invalid = [r for r in agent if r.status == "invalid"]
    models = sorted({a.model_id for a in attempts if a.model_id}) or [cfg.model]
    roles = [r["name"] for r in (cfg.roles or [])]
    times = sorted(a.started_at for a in attempts)
    when = ("during the study" if not times else f"on {times[0]:%Y-%m-%d}" if times[0].date() == times[-1].date() else f"between {times[0]:%Y-%m-%d} and {times[-1]:%Y-%m-%d}")
    retries = sum(1 for a in attempts if a.attempt_kind == "validation_retry")
    smp = ", ".join(f"{k}={v}" for k, v in (cfg.sampling or {}).items()) or "provider default sampling parameters"
    tol = f" (tolerance {cfg.tolerance:g} of the observed range)" if cfg.tolerance else ""
    rate = f"{len(invalid)} of {len(agent)} agent runs ({100 * len(invalid) / len(agent):.0f}%)" if agent else "no agent runs"
    arms = f"{cfg.reps} repetitions for each of {len(roles)} stakeholder roles ({'; '.join(roles)})" if roles else "no stakeholder-role runs"
    gen = f" and {cfg.reps} repetitions of a role-free generic prompt" if "generic" in (cfg.arms or []) else ""
    return (f"Generative AI was used in this study as a research instrument, not to analyse the data or to write the text. "
            f"The language model {', '.join(models)} ({cfg.provider}) was called through its API {when} to propose calibration anchors and "
            f"truth-table cutoffs, each with a written rationale. The design comprised {arms}{gen}. Each prompt contained the description of the "
            f"phenomenon, construct definitions, measurement instruments, summary statistics of each variable's observed distribution and, for "
            f"role runs, the description of the role; raw case data were not sent, and the model had no tools or retrieval. Sampling parameters: {smp}. "
            f"Each answer was validated structurally (JSON schema, anchor order for the declared direction, anchors within the observed range{tol}, "
            f"cutoff ranges, non-empty rationales). An answer that failed received exactly one further attempt with the validation errors appended "
            f"({retries} such retries were made; {rl} rate-limit retries are logged separately); a second failure was recorded as an invalid judgment "
            f"and not analysed: {rate}. Model output was never edited. Calibration, truth-table construction, necessity analysis and minimisation "
            f"were carried out by identical R code ({env.get('R') or 'R version in bundle'}, QCA {env.get('QCA') or 'version in bundle'}) that received "
            f"the anchors and cutoffs as arguments. Prompts, raw responses, decisions and a replication script are archived in the replication bundle.")


def build_report(session: Session, cfg_id: int) -> str:
    from app.api import service

    cfg = session.get(RunConfig, cfg_id)
    if cfg is None:
        raise KeyError(cfg_id)
    res = service.results(cfg_id)
    proj = res["project"]
    runs = session.query(Run).filter_by(run_config_id=cfg_id).all()
    attempts = [a for r in runs for a in r.attempts]
    rl = session.query(CallLog).join(Run, CallLog.run_id == Run.id).filter(Run.run_config_id == cfg_id, CallLog.kind == "rate_limit_retry").count()
    outs = [r.judgment.r_result.r_output for r in runs if r.judgment and r.judgment.r_result]
    v: dict[str, Any] = next((o["versions"] for o in outs if o.get("versions")), {})
    d = build_dashboard(res, "parsimonious")

    h = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>SA-QCA report, run {cfg_id}</title><style>"
         "body{font:15px/1.5 system-ui,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;color:#1d2329}"
         "table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}th,td{border-bottom:1px solid #d9dde1;padding:4px 8px;text-align:left;vertical-align:top}"
         "h2{margin-top:28px;border-bottom:2px solid #0072B2;padding-bottom:2px}.note{background:#f5f5f0;border:1px solid #d9dde1;padding:8px 12px;border-radius:6px}"
         "@media print{h2{break-after:avoid}table,svg{break-inside:avoid}}</style></head><body>",
         f"<h1>Stakeholder Anchors (SA-QCA): run {cfg_id}</h1>",
         "<p class='note'>SA-QCA is a candidate protocol for discussion, not a finished standard. Generated "
         f"{E(res['config']['created_at'])} from stored runs; see the replication bundle for the underlying files.</p>"]
    if cfg.provider == "demo-mock":
        h.append("<p class='note' style='border-color:#D55E00'><b>Scripted test run.</b> The anchors in this run came from a scripted stand-in, not a language model. "
                 "Nothing here is evidence about stakeholders or models.</p>")
    h.append("<h2>1. Project</h2>")
    h.append(f"<p><b>{E(proj['name'])}</b>: {proj['n_cases']} cases" + (f" ({proj['n_dropped']} rows dropped for missing values)" if proj.get("n_dropped") else "") +
             ". Dataset checksum (SHA-256): " +
             (f"<code>{E(str(proj['dataset_sha256'])[:16])}…</code>" if proj.get("dataset_sha256") else "not recorded (run predates project snapshots)") + "</p>")
    h.append(f"<p>{E(proj['case_description'])}</p>")
    h.append(_table(["Variable", "Role", "Direction", "Construct definition", "Instrument", "Observed range", "Original anchors / breakpoints"],
                    [[x["name"], x["role"], x["direction"], x["construct_definition"], x["instrument"], f"{x['stats']['min']} to {x['stats']['max']}",
                      ("fixed (already calibrated)" if x.get("calibration") == "precalibrated" else " / ".join(str(a) for a in proj["reference"].get(x["name"], {}).values()) or "none")] for x in proj["variables"]]))
    h.append("<h2>2. Method</h2><ol>"
             "<li>Stakeholder roles are derived from the study's own cases and approved by the researcher before anything runs.</li>"
             "<li>Judgment and computation are separate: a model supplies only calibration anchors and truth-table cutoffs; identical R code performs every calculation.</li>"
             "<li>Each agent receives the phenomenon, construct definitions, measurement instruments, observed distributions and its role.</li>"
             "<li>Baselines: a generic prompt without a role, and a mechanical perturbation of the analyst's anchors in the style of Skaaning (2011).</li>"
             "<li>Answers are validated structurally, never repaired; one retry with the error appended; a second failure is an invalid judgment.</li></ol>")
    h.append("<h2>3. Anchor sources</h2>")
    ap = cfg.role_approval or {}
    rows = [[f"Stakeholder: {r['name']}", r["description"]] for r in (cfg.roles or [])]
    if "generic" in (cfg.arms or []):
        rows.append(["Generic", "Same prompt without a role."])
    if "mechanical" in (cfg.arms or []):
        mp = cfg.mechanical_params or {}
        rows.append(["Mechanical", f"{mp.get('generator', '')}: each condition's anchors moved together to a lower/original/higher set "
                                   f"(offset {mp.get('shift_fraction')} of the observed range), crossed across conditions; outcome unchanged; "
                                   "frequency cutoff +1, consistency cutoff ±0.10. Parameters are this tool's, following Skaaning (2011)."])
    rows.append(["Analyst's original", "The analyst's own specification, run through the identical pipeline."])
    h.append(_table(["Source", "Description"], rows))
    if ap:
        h.append(f"<p>Roles approved by {E(str(ap.get('approved_by')))} at {E(str(ap.get('approved_at')))} (set fingerprint <code>{E(str(ap.get('roles_hash', ''))[:12])}…</code>).</p>")
    h.append(f"<p>Model {E(cfg.model)} ({E(cfg.provider)}); prompt template {E(cfg.template_version)}; {cfg.reps} repetitions per source; "
             f"sampling {E(str(cfg.sampling or 'provider default'))}; range tolerance {cfg.tolerance:g}; "
             f"{E(str(v.get('R')))}, QCA {E(str(v.get('QCA')))}.</p>")
    h.append("<h2>4. Results</h2>")
    h.append(f"<p>Analyst's original solution (parsimonious): <b>{E(str(d['reference_solution'] or 'unavailable'))}</b></p>")
    h.append("<h3>Solutions by source</h3>")
    g: dict[tuple[str, str], int] = Counter()
    for m in d["matrix"]:
        if m["solution"] is not None:
            g[(m["arm"], m["solution"])] += 1
    score = {s["run_id"]: s["score"] for s in d["similarity"]}
    sim_by = {(m["arm"], m["solution"]): score.get(m["run_id"]) for m in d["matrix"] if m["solution"] is not None}
    h.append(_table(["Source", "Solution", "Runs", "Similarity"],
                    [[source_label(a), sol, n, "–" if sim_by[(a, sol)] is None else f"{sim_by[(a, sol)]:.2f}"] for (a, sol), n in sorted(g.items())]))
    h.append("<h3>Survival of the analyst's paths</h3>")
    h.append(_table(["Path", *[source_label(a) for a in d["arms"]], "Across roles"],
                    [[r["path"], *["–" if r["share_by_arm"][a] is None else f"{r['share_by_arm'][a] * 100:.0f}%" for a in d["arms"]], r["across_roles"]] for r in d["robustness"]])
             if d["robustness"] else "<p>No reference solution.</p>")
    h.append("<h3>Similarity to the analyst's solution</h3><p>Similarity is scored from 0 to 1: 1 means a run found the same solution as the analyst's, and 0 means the two solutions share no terms (Jaccard similarity over solution terms). Each circle stands for all runs with the same score, and the number inside it shows how many runs that is.</p>")
    h.append(_sim_svg(d))
    h.append("<h2>5. Validation</h2>")
    h.append(_table(["Source", "Runs", "Invalid rate", "First-attempt failure", "Statuses", "Failure reasons"],
                    [[source_label(a), r["n_runs"], "–" if r["invalid_rate"] is None else f"{r['invalid_rate'] * 100:.0f}%",
                      "–" if r["first_attempt_failure_rate"] is None else f"{r['first_attempt_failure_rate'] * 100:.0f}%",
                      ", ".join(f"{k}: {n}" for k, n in r["status_counts"].items()), ", ".join(f"{k}: {n}" for k, n in r["failure_reasons"].items()) or "–"]
                     for a, r in res["report"].items()]))
    h.append("<h2>6. AI-use statement (draft, review and edit before use)</h2>")
    if cfg.provider == "demo-mock":
        h.append("<p class='note' style='border-color:#D55E00'><b>Do not use this statement.</b> This run used scripted test responses, not a language model; "
                 "the text below is only an illustration of what the statement will say for a real run.</p>")
    h.append(f"<p class='note'>{E(ai_use_statement(cfg, runs, attempts, v, rl))}</p>")
    h.append("</body></html>")
    return "".join(h)
