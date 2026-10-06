import { useEffect, useRef, useState } from 'react'
import { api, withSid, type AiSettings, type Demo, type Results, type Role, type RunReq, type Status, type Study } from './api'
import { Dashboard } from './Dashboard'
import { Hist } from './Hist'
import { Upload } from './Upload'
import { sourceLabel } from './labels'

const TIPS: Record<string, string> = {
  anchors: 'Three raw values that fix calibration: full non-membership (≈0.05), crossover (0.5), full membership (≈0.95).',
  invalid: 'An agent answer that failed structural validation twice. It is recorded, never repaired, and never sent to R.',
}
const Tip = ({ k, children }: { k: string; children: React.ReactNode }) => <abbr title={TIPS[k]} style={{ textDecorationStyle: 'dotted' }}>{children}</abbr>

export function DataStep({ project, projectId, study, hasDataset, configured, demoOnly, expert, onProject, onNext, onBack }: { project: Demo | null; projectId: string; study: Study; hasDataset: boolean; configured: boolean; demoOnly: boolean; expert: boolean; onProject: (p: Demo) => void; onNext: () => void; onBack: () => void }) {
  const [mode, setMode] = useState<'view' | 'map'>('view')
  const [setup, setSetup] = useState<Awaited<ReturnType<typeof api.setup>> | null>(null)
  const [err, setErr] = useState('')
  const isDemo = projectId === 'demo'
  const openMapping = async () => { try { setSetup(await api.setup(projectId)); setMode('map'); setErr('') } catch (e) { setErr(String(e).replace(/^Error: /, '')) } }
  useEffect(() => { setMode(!isDemo && hasDataset && !configured ? 'map' : 'view'); if (!isDemo && hasDataset && !configured) void openMapping() }, [projectId, hasDataset, configured]) // eslint-disable-line react-hooks/exhaustive-deps
  const nav = <div className="actions"><button className="secondary" onClick={onBack}>Back</button><button disabled={!configured} onClick={onNext}>Next: calibration</button></div>
  return (<section aria-labelledby="s1">
    <h2 id="s1">Step 4: Your data</h2>
    <p className="muted">Attach the data for your cases and map each column to a condition or the outcome from your plan. Your data stay on this machine; models only see definitions and summary statistics, never rows.</p>
    {err && <p role="alert" className="warn">{err}</p>}
    {!isDemo && !hasDataset && <>
      {demoOnly ? <p className="muted">Uploads are disabled on this public demo.</p> : <Upload attachTo={projectId} plan={study} onReady={(p) => { onProject(p); setMode('view') }} />}</>}
    {mode === 'map' && setup && <Upload key={projectId + (setup.upload.filename)} attachTo={projectId} plan={study} existing={{ info: setup.upload, config: setup.config ?? setup.draft_config ?? null }} unmatched={setup.draft_config?.unmatched_plan} onReady={(p) => { onProject(p); setMode('view') }} />}
    {mode === 'view' && project && <>
      {!isDemo && <div className="actions" style={{ justifyContent: 'flex-start' }}><button className="secondary" onClick={openMapping}>Edit the mapping and definitions</button></div>}
      <p>{project.name} · {project.n_cases} cases{project.n_dropped > 0 && ` (${project.n_dropped} rows dropped for missing values)`}. <span className="muted">{project.case_description}</span></p>
      {!project.has_reference && <p className="muted" role="note">No complete set of original anchors and cutoffs was given, so the mechanical source and the comparison with your own solution are unavailable.</p>}
      {project.warnings.length > 0 && <p role="alert" className="warn">Warning: {project.warnings.join('; ')}. Agents given little context tend to return a percentile rule.</p>}
      {project.variables.map((v) => (<div className="card" key={v.name}>
        <h3>{v.name} <span className="tag">{v.role}</span> <span className="tag">{v.direction}</span></h3>
        <div className="row"><div><p><b>Construct:</b> {v.construct_definition || <span className="warn">missing</span>}</p><p><b>Instrument:</b> {v.instrument || <span className="warn">missing</span>}</p>
          <p className="muted">min {v.stats.min} · Q1 {v.stats.q1.toFixed(2)} · median {v.stats.median.toFixed(2)} · Q3 {v.stats.q3.toFixed(2)} · max {v.stats.max} · mean {v.stats.mean.toFixed(2)}</p>
          {v.calibration === 'precalibrated' ? <p className="muted"><b>Already calibrated:</b> these membership scores are used exactly as given and stay fixed for every source.</p>
            : v.calibration === 'breakpoints' ? <p className="muted">Calibrated on a four-value scale (0 / 0.33 / 0.67 / 1). Your original breakpoints: {Object.values(project.reference[v.name] ?? {}).join(' / ') || 'not given'}</p>
            : <p className="muted">Your original <Tip k="anchors">anchors</Tip>: {Object.values(project.reference[v.name] ?? {}).join(' / ') || 'not given'}</p>}</div>
          <Hist stats={v.stats} marks={v.calibration === 'precalibrated' ? [] : Object.values(project.reference[v.name] ?? {})} label={`Histogram of ${v.name}${v.calibration === 'precalibrated' ? ' (membership scores)' : ' with your calibration marked'}`} /></div>
      </div>))}
      {expert && <pre>{JSON.stringify(project, null, 1)}</pre>}</>}
    {mode === 'view' && !project && hasDataset && <p className="muted">Finish the mapping above to continue.</p>}
    {nav}
  </section>)
}

export function CalibrationStep({ demoOnly, maxReps, demo, design, setDesign, roles, approved, ai, apiKey, openSettings, onStart, onBack, expert }: { demoOnly: boolean; maxReps: number; demo: Demo; design: RunReq; setDesign: (d: RunReq) => void; roles: Role[]; approved: boolean; ai: AiSettings; apiKey: string; openSettings: () => void; onStart: () => void; onBack: () => void; expert: boolean }) {
  const [preview, setPreview] = useState<{ prompt: string; sent_to_provider: string; template_version: string } | null>(null)
  const [pv, setPv] = useState('__generic__')
  const [est, setEst] = useState<Awaited<ReturnType<typeof api.estimate>> | null>(null)
  const [confirm, setConfirm] = useState(false)
  const up = (p: Partial<RunReq>) => { setDesign({ ...design, ...p }); setEst(null); setConfirm(false) }
  const anthropic = !demoOnly && ai.provider === 'anthropic'
  const canRun = confirm && est && (design.arms.roles.length === 0 || approved) && (!anthropic || apiKey) && (design.arms.roles.length + Number(design.arms.generic) + Number(design.arms.mechanical) > 0)
  useEffect(() => { api.preview(pv === '__generic__' ? null : roles.find((r) => r.name === pv) ?? null, demo.id).then(setPreview).catch(() => undefined) }, [pv, roles, demo.id])
  return (<section aria-labelledby="s3">
    <h2 id="s3">Step 5: Calibration across stakeholders</h2>
    <p className="muted">Each stakeholder you approved proposes its own calibration of your conditions and outcome, with written rationales. Choose the sources to compare, check exactly what will be sent, then confirm the estimate.</p>
    {!approved && <p role="alert" className="warn">Approve your stakeholders (step 2) to include them as sources.</p>}
    <div className="card"><h3>Anchor sources</h3>
      {roles.map((r) => <label key={r.name}><input type="checkbox" disabled={!approved} checked={design.arms.roles.includes(r.name)} onChange={(e) => up({ arms: { ...design.arms, roles: e.target.checked ? [...design.arms.roles, r.name] : design.arms.roles.filter((n) => n !== r.name) } })} /> Stakeholder: {r.name}</label>)}
      <label><input type="checkbox" checked={design.arms.generic} onChange={(e) => up({ arms: { ...design.arms, generic: e.target.checked } })} /> Generic (same prompt, no role)</label>
      <label><input type="checkbox" disabled={!demo.has_reference} checked={design.arms.mechanical && demo.has_reference} onChange={(e) => up({ arms: { ...design.arms, mechanical: e.target.checked } })} /> Mechanical (Skaaning-style perturbation of the analyst's anchors; no LLM){!demo.has_reference && <span className="warn"> needs your original anchors/breakpoints and cutoffs (step 4)</span>}</label></div>
    <div className="card"><h3>Model and sampling</h3>
      <p>{anthropic ? <>Calibration proposals will come from <b>{ai.model}</b>{apiKey ? '' : ' (enter your API key in AI settings)'}.</> : <>Calibration proposals will come from the <b>scripted stand-in</b> (not a language model). Its answers show how the tool works; they are not findings.</>} <button className="secondary" onClick={openSettings}>AI settings</button></p>
      <div className="row">
        <label>Repetitions per source<input type="number" min={1} max={maxReps} value={design.reps} onChange={(e) => up({ reps: Math.min(maxReps, Math.max(1, +e.target.value)) })} /></label>
        <label>Range tolerance (fraction of observed range)<input type="number" step="0.05" min={0} value={design.tolerance} onChange={(e) => up({ tolerance: +e.target.value })} /></label></div>
      {!demoOnly && anthropic && <div className="row"><label>Price in ($/M tokens)<input type="number" value={design.price_in ?? ''} onChange={(e) => up({ price_in: e.target.value === '' ? null : +e.target.value })} /></label>
        <label>Price out ($/M tokens)<input type="number" value={design.price_out ?? ''} onChange={(e) => up({ price_out: e.target.value === '' ? null : +e.target.value })} /></label>
        <label>Spend cap ($, needs prices)<input type="number" value={design.spend_cap ?? ''} onChange={(e) => up({ spend_cap: e.target.value === '' ? null : +e.target.value })} /></label></div>}</div>
    <div className="card"><h3>Exact prompt an agent will receive</h3>
      <label>Preview for<select value={pv} onChange={(e) => setPv(e.target.value)}><option value="__generic__">Generic (no role)</option>{roles.map((r) => <option key={r.name} value={r.name}>{r.name}</option>)}</select></label>
      {preview && <><p className="muted">Template {preview.template_version}. Sent to provider: {preview.sent_to_provider}.</p><pre tabIndex={0}>{preview.prompt}</pre></>}</div>
    <div className="card"><h3>Estimate and confirm</h3>
      <button className="secondary" onClick={async () => setEst(await api.estimate({ ...design, project_id: demo.id, arms: { ...design.arms, mechanical: design.arms.mechanical && demo.has_reference } }))}>Estimate cost and calls</button>
      {est && <p>{est.llm_calls_min}–{est.llm_calls_max} LLM calls (max counts one validation retry each) + {est.mechanical_runs} mechanical runs. ≈{est.approx_input_tokens_per_call} input / {est.approx_output_tokens_per_call} output tokens per call. {est.cost_usd_max !== null ? `Worst-case cost ≈ $${est.cost_usd_max.toFixed(2)}.` : 'Enter prices above to see a cost.'}</p>}
      <label><input type="checkbox" disabled={!est} checked={confirm} onChange={(e) => setConfirm(e.target.checked)} /> I have reviewed the prompt, data sent and estimate, and want to run.</label></div>
    <div className="actions"><button className="secondary" onClick={onBack}>Back</button><button disabled={!canRun} onClick={onStart}>Start the analysis</button></div>
    {expert && <pre>{JSON.stringify(design, null, 1)}</pre>}
  </section>)
}

export function RunStep({ runId, status, setStatus, onDone, goResults }: { runId: number | null; status: Status | null; setStatus: (s: Status) => void; onDone: (id: number) => Promise<void>; goResults: () => void }) {
  const called = useRef<number | null>(null)
  useEffect(() => {
    if (runId === null) return
    const es = new EventSource(withSid(`/api/runs/${runId}/events`))
    es.onmessage = (m) => { const s: Status = JSON.parse(m.data); setStatus(s); if (s.state !== 'running') { es.close(); if (called.current !== runId) { called.current = runId; void onDone(runId) } } }
    es.onerror = () => es.close()
    return () => es.close()
  }, [runId]) // eslint-disable-line react-hooks/exhaustive-deps
  if (runId === null) return <p>No analysis started yet. Set it up in step 5.</p>
  return (<section aria-labelledby="s4"><h2 id="s4">Step 6: Analysis</h2>
    <p className="muted">Every proposal goes through the same QCA code, one run at a time. Invalid answers are counted, not repaired.</p>
    {status && <><progress value={status.done} max={status.total} aria-label="Run progress" /> <p role="status">{status.done}/{status.total} runs · state: <b>{status.state}</b></p>
      <div className="actions" style={{ justifyContent: 'flex-start' }}>
        {status.state === 'running' && <button className="secondary" onClick={() => api.cancel(runId)}>Cancel</button>}
        {status.state !== 'running' && <button onClick={goResults}>View results</button>}</div>
      {status.provider_errors && status.provider_errors.length > 0 && <div role="alert" className="card"><p className="warn"><b>The model provider returned an error.</b> These runs are recorded as provider errors, not as invalid answers.</p>{status.provider_errors.map((e) => <pre key={e}>{e}</pre>)}</div>}
      <h3>Validation report (live)</h3>
      <table><thead><tr><th>Source</th><th>Runs</th><th>Statuses</th><th><Tip k="invalid">Invalid</Tip> rate</th><th>1st-attempt fail</th><th>Reasons</th></tr></thead><tbody>
        {Object.entries(status.report).map(([arm, r]) => <tr key={arm}><td>{sourceLabel(arm)}</td><td>{r.n_runs}</td><td>{Object.entries(r.status_counts).map(([k, v]) => `${k}: ${v}`).join(', ')}</td>
          <td>{r.invalid_rate === null ? '–' : `${(r.invalid_rate * 100).toFixed(0)}%`}</td><td>{r.first_attempt_failure_rate === null ? '–' : `${(r.first_attempt_failure_rate * 100).toFixed(0)}%`}</td><td>{Object.entries(r.failure_reasons).map(([k, v]) => `${k}: ${v}`).join(', ') || '–'}</td></tr>)}</tbody></table></>}
  </section>)
}

export function ResultsStep({ results, demo, expert, onNext }: { results: Results | null; demo: Demo; expert: boolean; onNext: () => void }) {
  if (!results) return <p>No results yet. Complete a run first.</p>
  return <><Dashboard results={results} demo={demo} />{expert && <pre>{JSON.stringify(results, null, 1)}</pre>}<div className="actions"><span /><button onClick={onNext}>Next: interpretation</button></div></>
}
