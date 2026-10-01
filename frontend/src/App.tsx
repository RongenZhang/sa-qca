import { useEffect, useRef, useState } from 'react'
import { api, withSid, type Demo, type Results, type Role, type RunReq, type Status } from './api'
import { Dashboard } from './Dashboard'
import { Hist } from './Hist'
import { Intro } from './Intro'
import { Upload } from './Upload'
import { sourceLabel } from './labels'

const STEPS = ['1 Data & variables', '2 Stakeholder roles', '3 Run design', '4 Run', '5 Results']
const TIPS: Record<string, string> = {
  crossover: 'The raw value where membership in the set is exactly 0.5 (maximum ambiguity).',
  anchors: 'Three raw values that fix calibration: full non-membership (≈0.05), crossover (0.5), full membership (≈0.95).',
  invalid: 'An agent answer that failed structural validation twice. It is recorded, never repaired, and never sent to R.',
}
// Per-tab convenience only (never the API key). Falls back silently if storage is unavailable.
function usePersisted<T>(key: string, init: T): [T, (v: T | ((p: T) => T)) => void] {
  const [v, set] = useState<T>(() => { try { const r = sessionStorage.getItem('saqca.' + key); return r ? (JSON.parse(r) as T) : init } catch { return init } })
  useEffect(() => { try { sessionStorage.setItem('saqca.' + key, JSON.stringify(v)) } catch { /* ignore */ } }, [key, v])
  return [v, set]
}
const Tip = ({ k, children }: { k: string; children: React.ReactNode }) => <abbr title={TIPS[k]} style={{ textDecorationStyle: 'dotted' }}>{children}</abbr>

export default function App() {
  const [step, setStep] = usePersisted('step', 0)
  const [demo, setDemo] = useState<Demo | null>(null)
  const [err, setErr] = useState('')
  const [expert, setExpert] = useState(false)
  const [roles, setRoles] = usePersisted<Role[]>('roles', [])
  const [approval, setApproval] = usePersisted<{ roles_hash: string; approved_by: string; approved_at: string; snapshot: string } | null>('approval', null)
  const [design, setDesign] = usePersisted<RunReq>('design', { project_id: 'demo', role_set_hash: '', arms: { roles: [], generic: true, mechanical: true }, reps: 3, provider: 'demo-mock', model: 'demo-mock-1', temperature: null, tolerance: 0, spend_cap: null, price_in: null, price_out: null })
  const [apiKey, setApiKey] = useState('') // memory only; never persisted
  const [workspaceId, setWorkspaceId] = useState('')
  const [mode, setMode] = useState<Awaited<ReturnType<typeof api.mode>> | null>(null)
  useEffect(() => { api.mode().then(setMode).catch(() => undefined) }, [])
  const demoOnly = mode?.mode === 'demo'
  const [runId, setRunId] = usePersisted<number | null>('runId', null)
  const [status, setStatus] = useState<Status | null>(null)
  const [results, setResults] = useState<Results | null>(null)

  const [showIntro, setShowIntro] = useState(() => { try { return localStorage.getItem('saqca.introSeen') !== '1' } catch { return true } })
  const closeIntro = () => { setShowIntro(false); try { localStorage.setItem('saqca.introSeen', '1') } catch { /* ignore */ } }
  const [projectId, setProjectId] = usePersisted('projectId', 'demo')
  useEffect(() => { api.project(projectId).then(setDemo).catch((e) => { setErr(String(e).replace(/^Error: /, '')); if (projectId !== 'demo') setProjectId('demo') }) }, [projectId, setProjectId])
  const switchProject = (p: Demo) => {
    if (p.id !== projectId) { setRunId(null); setStatus(null); setResults(null) }  // editing the same project keeps earlier runs on screen
    setProjectId(p.id); setDemo(p); setErr('')
    setDesign((d) => ({ ...d, project_id: p.id, arms: { ...d.arms, mechanical: p.has_reference && d.arms.mechanical } }))
  }
  const snapshot = JSON.stringify(roles.map((r) => [r.name, r.description]))
  const approved = approval !== null && approval.snapshot === snapshot
  const done = [!!demo, approved, false, status?.state === 'completed', !!results]

  return (
    <>
      <div className="banner" role="note">SA-QCA is a <b>candidate protocol for discussion</b>, not a finished standard. {demoOnly ? `Public demo: scripted responses only (no language model is called), synthetic data, nothing you type leaves this site, and runs are deleted after ${mode?.retention_hours} hours. To use your own data or a real model, run the tool locally. ` : demo?.is_demo && 'The demo data are synthetic. '}
        <button className="secondary" style={{ padding: '2px 10px' }} onClick={() => setShowIntro((v) => !v)} aria-expanded={showIntro}>About this tool</button>{' '}
        <label style={{ display: 'inline' }}><input type="checkbox" checked={expert} onChange={(e) => setExpert(e.target.checked)} /> Expert view (raw JSON)</label></div>
      <main>
        <h1>Stakeholder Anchors (SA-QCA)</h1>
        {showIntro && <Intro onClose={closeIntro} />}
        <nav aria-label="Protocol steps"><ol className="steps">
          {STEPS.map((s, i) => <li key={s} className={(i === step ? 'cur ' : '') + (done[i] ? 'done' : '')}><button aria-current={i === step ? 'step' : undefined} onClick={() => setStep(i)}>{s}</button></li>)}
        </ol></nav>
        {err && <p role="alert" className="warn">{err}</p>}
        {!demo ? <p>Loading…</p> : <>
          {step === 0 && <Step1 demo={demo} expert={expert} onProject={switchProject} demoOnly={demoOnly} />}
          {step === 1 && <Step2 roles={roles} setRoles={setRoles} approval={approval} approved={approved} onApprove={async (by) => { try { const a = await api.approve(roles, by); setApproval({ ...a, snapshot }); setDesign((d) => ({ ...d, role_set_hash: a.roles_hash, arms: { ...d.arms, roles: roles.map((r) => r.name) } })); setErr('') } catch (e) { setErr(String(e).replace(/^Error: /, '')) } }} />}
          {step === 2 && <Step3 demoOnly={demoOnly} maxReps={mode?.max_reps ?? 1000} demo={demo} design={design} setDesign={setDesign} roles={roles} approved={approved} apiKey={apiKey} setApiKey={setApiKey} workspaceId={workspaceId} setWorkspaceId={setWorkspaceId} expert={expert}
            onStart={async () => { try { const r = await api.start({ ...design, project_id: demo.id, role_set_hash: approval?.roles_hash ?? '' }, apiKey, workspaceId); setRunId(r.run_config_id); setStatus(null); setResults(null); setStep(3); setErr('') } catch (e) { setErr(String(e).replace(/^Error: /, '')) } }} />}
          {step === 3 && <Step4 runId={runId} status={status} setStatus={setStatus} onDone={async (id) => { setResults(await api.results(id)) }} goResults={() => setStep(4)} />}
          {step === 4 && <Step5 results={results} demo={results?.project ?? demo} expert={expert} />}
        </>}
      </main>
    </>
  )
}

function Step1({ demo, expert, onProject, demoOnly }: { demo: Demo; expert: boolean; onProject: (p: Demo) => void; demoOnly: boolean }) {
  const [mode, setMode] = useState<'current' | 'upload' | 'edit'>('current')
  const [existing, setExisting] = useState<Awaited<ReturnType<typeof api.setup>> | null>(null)
  return (<section aria-labelledby="s1">
    <h2 id="s1">Step 1: Data and variables</h2>
    <p className="muted">Describe the phenomenon and define your conditions and outcome. This is what every agent will read.</p>
    <div className="actions" style={{ justifyContent: 'flex-start' }}>
      <button className={mode === 'current' ? '' : 'secondary'} onClick={() => setMode('current')}>Current project</button>
      {!demoOnly && <button className={mode === 'upload' ? '' : 'secondary'} onClick={() => setMode('upload')}>Upload my own data</button>}
      {!demo.is_demo && <button className="secondary" onClick={async () => { setExisting(await api.setup(demo.id)); setMode('edit') }}>Edit project</button>}
      {!demo.is_demo && <button className="secondary" onClick={async () => onProject(await api.project('demo'))}>Switch to the demo project</button>}
    </div>
    {mode === 'upload' ? <Upload onReady={(p) => { onProject(p); setMode('current') }} /> : mode === 'edit' && existing ? <Upload key={demo.id} existing={{ info: existing.upload, config: existing.config }} onReady={(p) => { onProject(p); setMode('current') }} /> : <>
    <p>{demo.name} · {demo.n_cases} cases{demo.n_dropped > 0 && ` (${demo.n_dropped} rows dropped for missing values)`}. <span className="muted">{demo.case_description}</span></p>
    {!demo.has_reference && <p className="muted" role="note">No complete set of original anchors and cutoffs was given, so the mechanical source and the comparison with your published solution are unavailable for this project.</p>}
    <p className="muted">Data minimization: agents receive only the definitions, instruments and the summary statistics/histograms below. Raw rows are never sent.</p>
    {demo.warnings.length > 0 && <p role="alert" className="warn">Warning: {demo.warnings.join('; ')}. Agents given little context tend to return a percentile rule.</p>}
    {demo.variables.map((v) => (<div className="card" key={v.name}>
      <h3>{v.name} <span className="tag">{v.role}</span> <span className="tag">{v.direction}</span></h3>
      <div className="row"><div><p><b>Construct:</b> {v.construct_definition || <span className="warn">missing</span>}</p><p><b>Instrument:</b> {v.instrument || <span className="warn">missing</span>}</p>
        <p className="muted">min {v.stats.min} · Q1 {v.stats.q1.toFixed(2)} · median {v.stats.median.toFixed(2)} · Q3 {v.stats.q3.toFixed(2)} · max {v.stats.max} · mean {v.stats.mean.toFixed(2)}</p>
        <p className="muted">Analyst's original <Tip k="anchors">anchors</Tip>: {Object.values(demo.reference[v.name] ?? {}).join(' / ')}</p></div>
        <Hist stats={v.stats} marks={Object.values(demo.reference[v.name] ?? {})} label={`Histogram of ${v.name} with the analyst's anchors marked`} /></div>
    </div>))}
    {expert && <pre>{JSON.stringify(demo, null, 1)}</pre>}</>}
  </section>)
}

function Step2({ roles, setRoles, approval, approved, onApprove }: { roles: Role[]; setRoles: (r: Role[]) => void; approval: { roles_hash: string; approved_by: string; approved_at: string } | null; approved: boolean; onApprove: (by: string) => void }) {
  const [by, setBy] = useState('')
  const set = (i: number, p: Partial<Role>) => setRoles(roles.map((r, k) => (k === i ? { ...r, ...p } : r)))
  const move = (i: number, d: number) => { const a = [...roles]; const j = i + d; if (j < 0 || j >= a.length) return; [a[i], a[j]] = [a[j], a[i]]; setRoles(a) }
  return (<section aria-labelledby="s2">
    <h2 id="s2">Step 2: Stakeholder roles</h2>
    <p className="muted">Roles come from your own cases, not from us. Nothing runs until you approve them.</p>
    <p className="muted">Roles come from the study's own cases and constructs. Write them yourself, or ask for suggestions (AI-generated, editable). Nothing runs until you approve the set.</p>
    <div className="actions" style={{ justifyContent: 'flex-start' }}>
      <button className="secondary" onClick={async () => { const s = await api.suggest(); setRoles([...roles, ...s.roles.map((r) => ({ ...r, ai: true }))]) }}>Suggest roles (AI)</button>
      <button className="secondary" onClick={() => setRoles([...roles, { name: '', description: '', relevance: '' }])}>Add role</button>
    </div>
    {roles.map((r, i) => (<div className="card" key={i}>
      <div className="row"><label>Name{r.ai && <> <span className="tag ai">AI-generated · editable</span></>}<input value={r.name} onChange={(e) => set(i, { name: e.target.value })} /></label>
        <label>Why relevant (optional)<input value={r.relevance} onChange={(e) => set(i, { relevance: e.target.value })} /></label></div>
      <label>Vantage-point description<textarea rows={3} value={r.description} onChange={(e) => set(i, { description: e.target.value })} /></label>
      <div className="actions" style={{ justifyContent: 'flex-start' }}>
        <button className="secondary" onClick={() => move(i, -1)} aria-label={`Move ${r.name || 'role'} up`}>↑</button>
        <button className="secondary" onClick={() => move(i, 1)} aria-label={`Move ${r.name || 'role'} down`}>↓</button>
        <button className="secondary" onClick={() => setRoles(roles.filter((_, k) => k !== i))}>Delete</button>
        {i > 0 && <button className="secondary" onClick={() => { const a = roles[i - 1]; setRoles([...roles.slice(0, i - 1), { ...a, name: `${a.name} + ${r.name}`, description: `${a.description}\n${r.description}` }, ...roles.slice(i + 1)]) }}>Merge into previous</button>}
      </div></div>))}
    <div className="card">
      <div className="row"><label>Approved by<input value={by} onChange={(e) => setBy(e.target.value)} placeholder="Your name" /></label>
        <button disabled={!roles.length || !by.trim() || roles.some((r) => !r.name.trim() || !r.description.trim())} onClick={() => onApprove(by)}>Approve roles</button></div>
      {approved && approval && <p className="ok" role="status">Locked: approved by {approval.approved_by} at {approval.approved_at}. Set fingerprint {approval.roles_hash.slice(0, 12)}…</p>}
      {!approved && approval && <p className="warn" role="status">Roles changed since approval; approve again before running.</p>}
    </div>
  </section>)
}

function Step3({ demoOnly, maxReps, demo, design, setDesign, roles, approved, apiKey, setApiKey, workspaceId, setWorkspaceId, onStart, expert }: { demoOnly: boolean; maxReps: number; workspaceId: string; setWorkspaceId: (v: string) => void; demo: Demo; design: RunReq; setDesign: (d: RunReq) => void; roles: Role[]; approved: boolean; apiKey: string; setApiKey: (k: string) => void; onStart: () => void; expert: boolean }) {
  const [preview, setPreview] = useState<{ prompt: string; sent_to_provider: string; template_version: string } | null>(null)
  const [pv, setPv] = useState('__generic__')
  const [est, setEst] = useState<Awaited<ReturnType<typeof api.estimate>> | null>(null)
  const [confirm, setConfirm] = useState(false)
  const up = (p: Partial<RunReq>) => { setDesign({ ...design, ...p }); setEst(null); setConfirm(false) }
  const anthropic = design.provider === 'anthropic'
  const canRun = confirm && est && (design.arms.roles.length === 0 || approved) && (!anthropic || apiKey) && (design.arms.roles.length + Number(design.arms.generic) + Number(design.arms.mechanical) > 0)
  useEffect(() => { api.preview(pv === '__generic__' ? null : roles.find((r) => r.name === pv) ?? null, demo.id).then(setPreview).catch(() => undefined) }, [pv, roles, demo.id])
  return (<section aria-labelledby="s3">
    <h2 id="s3">Step 3: Run design</h2>
    <p className="muted">Choose the anchor sources, check exactly what will be sent, then confirm the estimate.</p>
    {!approved && <p role="alert" className="warn">Approve stakeholder roles first (step 2) to include stakeholder sources.</p>}
    <div className="card"><h3>Anchor sources</h3>
      {roles.map((r) => <label key={r.name}><input type="checkbox" disabled={!approved} checked={design.arms.roles.includes(r.name)} onChange={(e) => up({ arms: { ...design.arms, roles: e.target.checked ? [...design.arms.roles, r.name] : design.arms.roles.filter((n) => n !== r.name) } })} /> Stakeholder: {r.name}</label>)}
      <label><input type="checkbox" checked={design.arms.generic} onChange={(e) => up({ arms: { ...design.arms, generic: e.target.checked } })} /> Generic (same prompt, no role)</label>
      <label><input type="checkbox" disabled={!demo.has_reference} checked={design.arms.mechanical && demo.has_reference} onChange={(e) => up({ arms: { ...design.arms, mechanical: e.target.checked } })} /> Mechanical (Skaaning-style perturbation of the analyst's anchors; no LLM){!demo.has_reference && <span className="warn"> needs the analyst's original anchors and cutoffs (step 1)</span>}</label></div>
    <div className="card"><h3>Model and sampling</h3><div className="row">
      <label>Provider<select value={design.provider} onChange={(e) => up({ provider: e.target.value, model: e.target.value === 'anthropic' ? 'claude-opus-5-5' : 'demo-mock-1' })}><option value="demo-mock">Scripted test responses (no key; not real LLM output)</option>{!demoOnly && <option value="anthropic">Anthropic</option>}</select></label>
      <label>Model<input value={design.model} onChange={(e) => up({ model: e.target.value })} /></label>
      <label>Repetitions per source<input type="number" min={1} max={maxReps} value={design.reps} onChange={(e) => up({ reps: Math.min(maxReps, Math.max(1, +e.target.value)) })} /></label>
      <label>Temperature (blank = provider default)<input type="number" step="0.1" value={design.temperature ?? ''} onChange={(e) => up({ temperature: e.target.value === '' ? null : +e.target.value })} /></label>
      <label>Range tolerance (fraction of observed range)<input type="number" step="0.05" min={0} value={design.tolerance} onChange={(e) => up({ tolerance: +e.target.value })} /></label></div>
      {anthropic && <label>API key (kept in this tab's memory only; sent per request)<input type="password" autoComplete="off" value={apiKey} onChange={(e) => setApiKey(e.target.value)} /></label>}
      {anthropic && <label>Workspace ID (only if the provider says your key is not scoped to a workspace)<input autoComplete="off" value={workspaceId} onChange={(e) => setWorkspaceId(e.target.value)} placeholder="wrkspc_…" /></label>}
      {!demoOnly && <div className="row"><label>Price in ($/M tokens)<input type="number" value={design.price_in ?? ''} onChange={(e) => up({ price_in: e.target.value === '' ? null : +e.target.value })} /></label>
        <label>Price out ($/M tokens)<input type="number" value={design.price_out ?? ''} onChange={(e) => up({ price_out: e.target.value === '' ? null : +e.target.value })} /></label>
        <label>Spend cap ($, needs prices)<input type="number" value={design.spend_cap ?? ''} onChange={(e) => up({ spend_cap: e.target.value === '' ? null : +e.target.value })} /></label></div>}</div>
    <div className="card"><h3>Exact prompt an agent will receive</h3>
      <label>Preview for<select value={pv} onChange={(e) => setPv(e.target.value)}><option value="__generic__">Generic (no role)</option>{roles.map((r) => <option key={r.name} value={r.name}>{r.name}</option>)}</select></label>
      {preview && <><p className="muted">Template {preview.template_version}. Sent to provider: {preview.sent_to_provider}.</p><pre tabIndex={0}>{preview.prompt}</pre></>}</div>
    <div className="card"><h3>Estimate and confirm</h3>
      <button className="secondary" onClick={async () => setEst(await api.estimate({ ...design, project_id: demo.id, arms: { ...design.arms, mechanical: design.arms.mechanical && demo.has_reference } }))}>Estimate cost and calls</button>
      {est && <p>{est.llm_calls_min}–{est.llm_calls_max} LLM calls (max counts one validation retry each) + {est.mechanical_runs} mechanical runs. ≈{est.approx_input_tokens_per_call} input / {est.approx_output_tokens_per_call} output tokens per call. {est.cost_usd_max !== null ? `Worst-case cost ≈ $${est.cost_usd_max.toFixed(2)}.` : 'Enter prices above to see a cost.'}</p>}
      <label><input type="checkbox" disabled={!est} checked={confirm} onChange={(e) => setConfirm(e.target.checked)} /> I have reviewed the prompt, data sent and estimate, and want to run.</label></div>
    <div className="actions"><span /><button disabled={!canRun} onClick={onStart}>Start run</button></div>
    {expert && <pre>{JSON.stringify(design, null, 1)}</pre>}
  </section>)
}

function Step4({ runId, status, setStatus, onDone, goResults }: { runId: number | null; status: Status | null; setStatus: (s: Status) => void; onDone: (id: number) => Promise<void>; goResults: () => void }) {
  const called = useRef<number | null>(null)
  useEffect(() => {
    if (runId === null) return
    const es = new EventSource(withSid(`/api/runs/${runId}/events`))
    es.onmessage = (m) => { const s: Status = JSON.parse(m.data); setStatus(s); if (s.state !== 'running') { es.close(); if (called.current !== runId) { called.current = runId; void onDone(runId) } } }
    es.onerror = () => es.close()
    return () => es.close()
  }, [runId]) // eslint-disable-line react-hooks/exhaustive-deps
  if (runId === null) return <p>No run started yet. Configure one in step 3.</p>
  return (<section aria-labelledby="s4"><h2 id="s4">Step 4: Run</h2>
    <p className="muted">Runs complete one by one. Invalid answers are counted, not repaired.</p>
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

function Step5({ results, demo, expert }: { results: Results | null; demo: Demo; expert: boolean }) {
  if (!results) return <p>No results yet. Complete a run first.</p>
  return <><Dashboard results={results} demo={demo} />{expert && <pre>{JSON.stringify(results, null, 1)}</pre>}</>
}
