import { useEffect, useRef, useState } from 'react'
import { AiSettingsPanel, DEFAULT_AI } from './AiSettings'
import { api, type AiSettings, type Demo, type Results, type RunReq, type Status, type Study, type StudyListItem, type StudyState } from './api'
import { Intro } from './Intro'
import { InterpretStep } from './Interpret'
import { CalibrationStep, DataStep, ResultsStep, RunStep } from './Steps'
import { ConditionsStep, StakeholdersStep, StudyStep, type SaveState } from './Study'

const STEPS = ['1 Question', '2 Stakeholders', '3 Conditions', '4 Data', '5 Calibration', '6 Analysis', '7 Results', '8 Interpretation']
const clean = (e: unknown) => String(e).replace(/^Error: /, '')

// Per-tab convenience only (never the API key). Falls back silently if storage is unavailable.
function usePersisted<T>(key: string, init: T): [T, (v: T | ((p: T) => T)) => void] {
  const [v, set] = useState<T>(() => { try { const r = sessionStorage.getItem('saqca.' + key); return r ? (JSON.parse(r) as T) : init } catch { return init } })
  useEffect(() => { try { sessionStorage.setItem('saqca.' + key, JSON.stringify(v)) } catch { /* ignore */ } }, [key, v])
  return [v, set]
}

export default function App() {
  const [step, setStep] = usePersisted('step', 0)
  const [projectId, setProjectId] = usePersisted('projectId', 'demo')
  const [state, setState] = useState<StudyState | null>(null)     // what the server holds for this study
  const [study, setStudy] = useState<Study | null>(null)          // the editable copy
  const [name, setName] = useState('')
  const [saveState, setSaveState] = useState<SaveState>('saved')
  const dirty = useRef(false)
  const [project, setProject] = useState<Demo | null>(null)       // the configured project (variables, statistics); null until the data step is done
  const [studies, setStudies] = useState<StudyListItem[]>([])
  const [err, setErr] = useState('')
  const [expert, setExpert] = useState(false)
  const [approval, setApproval] = usePersisted<{ roles_hash: string; approved_by: string; approved_at: string; snapshot: string } | null>('approval', null)
  const [design, setDesign] = usePersisted<RunReq>('design', { project_id: 'demo', role_set_hash: '', arms: { roles: [], generic: true, mechanical: true }, reps: 3, provider: 'demo-mock', model: 'demo-mock-1', temperature: null, tolerance: 0, spend_cap: null, price_in: null, price_out: null })
  const [ai, setAi] = usePersisted<AiSettings>('ai', DEFAULT_AI)
  const [apiKey, setApiKey] = useState('') // memory only; never persisted
  const [workspaceId, setWorkspaceId] = useState('')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [mode, setMode] = useState<Awaited<ReturnType<typeof api.mode>> | null>(null)
  useEffect(() => { api.mode().then(setMode).catch(() => undefined) }, [])
  const demoOnly = mode?.mode === 'demo'
  const [runId, setRunId] = usePersisted<number | null>('runId', null)
  const [status, setStatus] = useState<Status | null>(null)
  const [results, setResults] = useState<Results | null>(null)
  const [showIntro, setShowIntro] = useState(() => { try { return localStorage.getItem('saqca.introSeen') !== '1' } catch { return true } })
  const closeIntro = () => { setShowIntro(false); try { localStorage.setItem('saqca.introSeen', '1') } catch { /* ignore */ } }

  useEffect(() => {  // a link such as /?project=p_abc123 (printed by `python -m app.cli load-project`) opens that study
    const p = new URLSearchParams(window.location.search).get('project')
    if (p) { setProjectId(p); window.history.replaceState({}, '', window.location.pathname) }
  }, [setProjectId])

  // Load the study (plan) and, if its variables are set up, the configured project.
  useEffect(() => {
    let cancelled = false
    dirty.current = false
    setState(null); setStudy(null); setProject(null)
    api.getStudy(projectId).then(async (st) => {
      if (cancelled) return
      setState(st); setStudy(st.study); setName(st.name); setSaveState(st.read_only ? 'readonly' : 'saved'); setErr('')
      if (st.configured) { try { const p = await api.project(projectId); if (!cancelled) setProject(p) } catch (e) { if (!cancelled) setErr(clean(e)) } }
    }).catch((e) => { if (cancelled) return; setErr(clean(e)); if (projectId !== 'demo') setProjectId('demo') })
    return () => { cancelled = true }
  }, [projectId, setProjectId])
  useEffect(() => { api.studies().then(setStudies).catch(() => setStudies([])) }, [projectId, state?.name])

  // Autosave the plan (not for the read-only demo study).
  useEffect(() => {
    if (!study || !state || state.read_only || !dirty.current) return
    setSaveState('saving')
    const t = setTimeout(() => { api.putStudy(projectId, study, name).then(() => setSaveState('saved')).catch((e) => { setSaveState('error'); setErr(clean(e)) }) }, 700)
    return () => clearTimeout(t)
  }, [study, name]) // eslint-disable-line react-hooks/exhaustive-deps

  const update = (patch: Partial<Study>) => { dirty.current = true; setStudy((s) => (s ? { ...s, ...patch } : s)) }
  const rename = (n: string) => { dirty.current = true; setName(n) }
  const roles = study?.stakeholders ?? []
  const setRoles = (r: Study['stakeholders']) => update({ stakeholders: r })
  const snapshot = JSON.stringify(roles.map((r) => [r.name, r.description]))
  const approved = approval !== null && approval.snapshot === snapshot
  const openStudy = (id: string) => { setRunId(null); setStatus(null); setResults(null); setProjectId(id); setDesign((d) => ({ ...d, project_id: id })); if (id !== projectId) setStep(id === 'demo' ? 0 : 0) }
  const newStudy = async () => { try { const r = await api.newStudy('Untitled study'); openStudy(r.project_id) } catch (e) { setErr(clean(e)) } }
  const onProject = (p: Demo) => {
    setProject(p); setState((s) => (s ? { ...s, configured: true, has_dataset: true } : s)); setErr('')
    setDesign((d) => ({ ...d, project_id: p.id, arms: { ...d.arms, mechanical: p.has_reference && d.arms.mechanical } }))
    api.getStudy(projectId).then(setState).catch(() => undefined)
  }
  const planned = !!study && study.phenomenon.trim().length >= 20 && !!study.outcome.name.trim()
  const done = [planned, approved, !!study?.conditions.length, !!state?.configured, false, status?.state === 'completed', !!results, false]
  const needData = <div className="card"><p>Finish the data step first: attach your data and map it to your conditions and outcome.</p><button onClick={() => setStep(3)}>Go to the data step</button></div>
  const start = async () => {
    try {
      const provider = demoOnly || ai.provider === 'scripted' ? 'demo-mock' : 'anthropic'
      const r = await api.start({ ...design, project_id: projectId, provider, model: provider === 'anthropic' ? ai.model : 'demo-mock-1', temperature: ai.temperature, role_set_hash: approval?.roles_hash ?? '' }, apiKey, workspaceId)
      setRunId(r.run_config_id); setStatus(null); setResults(null); setStep(5); setErr('')
    } catch (e) { setErr(clean(e)) }
  }
  const common = { projectId, study: study as Study, update, readOnly: !!state?.read_only, ai, apiKey, workspace: workspaceId }

  return (
    <>
      <div className="banner" role="note">SA-QCA is a <b>candidate protocol for discussion</b>, not a finished standard. {demoOnly ? `Public demo: scripted responses only (no language model is called), synthetic data, nothing you type leaves this site, and runs are deleted after ${mode?.retention_hours} hours. To use your own question, data or a real model, run the tool locally. ` : projectId === 'demo' && 'This is the demo study (synthetic data). '}
        <button className="secondary" style={{ padding: '2px 10px' }} onClick={() => setShowIntro((v) => !v)} aria-expanded={showIntro}>About this tool</button>{' '}
        <button className="secondary" style={{ padding: '2px 10px' }} onClick={() => setSettingsOpen((v) => !v)} aria-expanded={settingsOpen}>AI settings</button>{' '}
        <label style={{ display: 'inline' }}><input type="checkbox" checked={expert} onChange={(e) => setExpert(e.target.checked)} /> Expert view (raw JSON)</label></div>
      <main>
        <h1>Stakeholder Anchors (SA-QCA)</h1>
        {showIntro && <Intro onClose={closeIntro} />}
        {settingsOpen && <AiSettingsPanel ai={ai} setAi={setAi} apiKey={apiKey} setApiKey={setApiKey} workspace={workspaceId} setWorkspace={setWorkspaceId} demoOnly={demoOnly} onClose={() => setSettingsOpen(false)} />}
        <nav aria-label="Protocol steps"><ol className="steps">
          {STEPS.map((s, i) => <li key={s} className={(i === step ? 'cur ' : '') + (done[i] ? 'done' : '')}><button aria-current={i === step ? 'step' : undefined} onClick={() => setStep(i)}>{s}</button></li>)}
        </ol></nav>
        {err && <p role="alert" className="warn">{err}</p>}
        {!study || !state ? <p>Loading…</p> : <>
          {step === 0 && <StudyStep projectId={projectId} name={name} setName={rename} study={study} update={update} readOnly={state.read_only} saveState={saveState} studies={studies} demoOnly={demoOnly} onNew={newStudy} onOpen={openStudy} onNext={() => setStep(1)} />}
          {step === 1 && <StakeholdersStep {...common} roles={roles} setRoles={setRoles} approval={approval} approved={approved} onNext={() => setStep(2)} onBack={() => setStep(0)}
            onApprove={async (by) => { try { const a = await api.approve(roles, by); setApproval({ ...a, snapshot }); setDesign((d) => ({ ...d, role_set_hash: a.roles_hash, arms: { ...d.arms, roles: roles.map((r) => r.name) } })); setErr('') } catch (e) { setErr(clean(e)) } }} />}
          {step === 2 && <ConditionsStep {...common} roles={roles} onNext={() => setStep(3)} onBack={() => setStep(1)} />}
          {step === 3 && <DataStep project={project} projectId={projectId} study={study} hasDataset={state.has_dataset} configured={state.configured} demoOnly={demoOnly} expert={expert} onProject={onProject} onNext={() => setStep(4)} onBack={() => setStep(2)} />}
          {step === 4 && (project ? <CalibrationStep demoOnly={demoOnly} maxReps={mode?.max_reps ?? 1000} demo={project} design={design} setDesign={setDesign} roles={roles} approved={approved} ai={ai} apiKey={apiKey} openSettings={() => setSettingsOpen(true)} expert={expert} onBack={() => setStep(3)} onStart={start} /> : needData)}
          {step === 5 && <RunStep runId={runId} status={status} setStatus={setStatus} onDone={async (id) => { setResults(await api.results(id)) }} goResults={() => setStep(6)} />}
          {step === 6 && (project || results ? <ResultsStep results={results} demo={results?.project ?? (project as Demo)} expert={expert} onNext={() => setStep(7)} /> : needData)}
          {step === 7 && <InterpretStep runId={results ? results.config.id : null} ai={ai} apiKey={apiKey} workspace={workspaceId} demoOnly={demoOnly} onBack={() => setStep(6)} />}
        </>}
      </main>
    </>
  )
}
