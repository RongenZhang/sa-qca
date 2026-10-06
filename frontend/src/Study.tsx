import { useState } from 'react'
import { AssistPanel } from './Assist'
import type { AiSettings, Calibration, PlanCondition, Role, Study, StudyListItem } from './api'

const NAME_RE = /^[A-Za-z][A-Za-z0-9_]*$/
export type SaveState = 'saved' | 'saving' | 'error' | 'readonly'
type Common = { projectId: string; study: Study; update: (patch: Partial<Study>) => void; readOnly: boolean; ai: AiSettings; apiKey: string; workspace: string }

const SaveBadge = ({ s }: { s: SaveState }) => <span className="muted" role="status">{s === 'saving' ? 'Saving…' : s === 'saved' ? 'Saved' : s === 'error' ? 'Could not save' : 'Demo study: edits are not saved'}</span>

// ---------------------------------------------------------------------------------------------------- Step 1
export function StudyStep({ projectId, name, setName, study, update, readOnly, saveState, studies, demoOnly, onNew, onOpen, onNext }: {
  projectId: string; name: string; setName: (n: string) => void; study: Study; update: (patch: Partial<Study>) => void; readOnly: boolean; saveState: SaveState
  studies: StudyListItem[]; demoOnly: boolean; onNew: () => void; onOpen: (id: string) => void; onNext: () => void
}) {
  const n = study.phenomenon.trim().length
  const o = study.outcome
  const bad = o.name.trim() !== '' && !NAME_RE.test(o.name.trim())
  return (
    <section aria-labelledby="s-study">
      <h2 id="s-study">Step 1: Your question</h2>
      <p className="muted">Describe the phenomenon you want to understand and the outcome you care about. Every later step builds on this text: the stakeholders, the conditions and the context each stakeholder reads.</p>
      <div className="card">
        <div className="row"><label>Study<input value={name} disabled={readOnly} onChange={(e) => setName(e.target.value)} /></label>
          <div className="actions" style={{ marginTop: 0, justifyContent: 'flex-start', alignItems: 'end' }}>
            {!demoOnly && <button className="secondary" onClick={onNew}>New study</button>}
            {projectId !== 'demo' && <button className="secondary" onClick={() => onOpen('demo')}>Use the demo study</button>}</div></div>
        {studies.length > 0 && !demoOnly && <label>Open a saved study<select value="" onChange={(e) => e.target.value && onOpen(e.target.value)}>
          <option value="">Choose…</option>{studies.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.created_at.slice(0, 10)}{s.outcome ? ` · ${s.outcome}` : ''})</option>)}</select></label>}
        <p><SaveBadge s={saveState} /></p>
      </div>
      <div className="card">
        <label>Phenomenon and context
          <textarea rows={9} value={study.phenomenon} disabled={readOnly} onChange={(e) => update({ phenomenon: e.target.value })} aria-describedby="phen-help" /></label>
        <p id="phen-help" className="muted">{n} characters. Say who or what the cases are, the setting and period, what the process or decision involves, and how the outcome shows up in practice. A few paragraphs works best. Do <b>not</b> include your findings, hypotheses or which combinations matter: stakeholders and models should not know the answer.</p>
        {n > 0 && n < 400 && <p className="warn" role="note">This is short ({n} characters). Suggestions and the stakeholders' readings are only as good as this description.</p>}
        <details><summary>An example of a useful description</summary>
          <p className="muted">"The cases are 40 mid-sized hospitals in one region. During 2023 each was offered the same electronic triage tool. Adoption was a decision for each emergency department, usually after a pilot, and it meant retraining nurses, changing intake routines and linking to patient records. Hospitals differ in how much training they gave, how visibly leaders sponsored the change, and how much staff time was freed for it. Adoption is observed at the end of the year as how consistently the tool is used at triage."</p></details>
      </div>
      <div className="card">
        <h3>The outcome of interest</h3>
        <div className="row"><label>Short name (letters, digits, underscores)<input value={o.name} disabled={readOnly} onChange={(e) => update({ outcome: { ...o, name: e.target.value } })} placeholder="e.g. ADOPTION" aria-invalid={bad} /></label>
          <label>How is it calibrated?<select value={o.calibration ?? 'direct'} disabled={readOnly} onChange={(e) => update({ outcome: { ...o, calibration: e.target.value as Calibration } })}>
            <option value="direct">Raw measure, three anchors (direct)</option><option value="breakpoints">Raw measure, breakpoints (four-value scale)</option></select></label>
          <label>Direction<select value={o.direction ?? 'positive'} disabled={readOnly} onChange={(e) => update({ outcome: { ...o, direction: e.target.value as 'positive' | 'negative' } })}>
            <option value="positive">Positive (higher value = more of the outcome)</option><option value="negative">Negative (higher value = less)</option></select></label></div>
        {bad && <p className="warn" role="alert">Names must start with a letter and use only letters, digits and underscores (a QCA requirement).</p>}
        <label>What the outcome means<textarea rows={3} value={o.description} disabled={readOnly} onChange={(e) => update({ outcome: { ...o, description: e.target.value } })} placeholder="e.g. How consistently clinicians use the tool at triage" /></label>
        <label>How it is (or will be) measured<textarea rows={2} value={o.how_to_measure ?? ''} disabled={readOnly} onChange={(e) => update({ outcome: { ...o, how_to_measure: e.target.value } })} placeholder="e.g. share of triage events recorded with the tool, from the system log" /></label>
      </div>
      <div className="actions"><span /><button disabled={n < 20 || !o.name.trim() || bad} onClick={onNext}>Next: stakeholders</button></div>
    </section>)
}

// ---------------------------------------------------------------------------------------------------- Step 2
export function StakeholdersStep({ roles, setRoles, approval, approved, onApprove, onNext, onBack, ...c }: Common & {
  roles: Role[]; setRoles: (r: Role[]) => void; approval: { roles_hash: string; approved_by: string; approved_at: string } | null; approved: boolean; onApprove: (by: string) => void; onNext: () => void; onBack: () => void
}) {
  const [by, setBy] = useState('')
  const set = (i: number, p: Partial<Role>) => setRoles(roles.map((r, k) => (k === i ? { ...r, ...p } : r)))
  const move = (i: number, d: number) => { const a = [...roles]; const j = i + d; if (j < 0 || j >= a.length) return; [a[i], a[j]] = [a[j], a[i]]; setRoles(a) }
  const ready = c.study.phenomenon.trim().length >= 20
  return (
    <section aria-labelledby="s-stake">
      <h2 id="s-stake">Step 2: Stakeholders</h2>
      <p className="muted">Stakeholders are groups who would defensibly read your measures differently: what counts as high or low, what evidence is convincing. Each will later propose its own calibration, so choose groups whose vantage points could lead to different, reasonable calibrations. Draw them from your own cases, not from outside categories.</p>
      <AssistPanel kind="stakeholders" label="stakeholders" projectId={c.projectId} ai={c.ai} apiKey={c.apiKey} workspace={c.workspace} ready={ready} notReady="Describe your phenomenon in step 1 first."
        inputs={{ phenomenon: c.study.phenomenon, outcome: { name: c.study.outcome.name, description: c.study.outcome.description }, existing: roles.map((r) => ({ name: r.name, description: r.description })), count: 5 }}
        describe={(it) => ({ title: it.name, body: it.description })}
        onAdd={(items, res) => setRoles([...roles, ...items.map((it) => ({ name: it.name, description: it.description, relevance: it.relevance ?? '', ai: res.ai_generated }))])} />
      <div className="actions" style={{ justifyContent: 'flex-start' }}><button className="secondary" onClick={() => setRoles([...roles, { name: '', description: '', relevance: '' }])}>Add a stakeholder yourself</button></div>
      {roles.map((r, i) => (<div className="card" key={i}>
        <div className="row"><label>Name{r.ai && <> <span className="tag ai">AI-generated · editable</span></>}<input value={r.name} onChange={(e) => set(i, { name: e.target.value })} /></label>
          <label>Why relevant (optional)<input value={r.relevance} onChange={(e) => set(i, { relevance: e.target.value })} /></label></div>
        <label>Vantage-point description<textarea rows={3} value={r.description} onChange={(e) => set(i, { description: e.target.value })} /></label>
        <div className="actions" style={{ justifyContent: 'flex-start' }}>
          <button className="secondary" onClick={() => move(i, -1)} aria-label={`Move ${r.name || 'stakeholder'} up`}>↑</button>
          <button className="secondary" onClick={() => move(i, 1)} aria-label={`Move ${r.name || 'stakeholder'} down`}>↓</button>
          <button className="secondary" onClick={() => setRoles(roles.filter((_, k) => k !== i))}>Delete</button>
          {i > 0 && <button className="secondary" onClick={() => { const a = roles[i - 1]; setRoles([...roles.slice(0, i - 1), { ...a, name: `${a.name} + ${r.name}`, description: `${a.description}\n${r.description}` }, ...roles.slice(i + 1)]) }}>Merge into previous</button>}
        </div></div>))}
      <div className="card">
        <h3>Approve the stakeholders</h3>
        <p className="muted">Approving locks this set for the runs. Nothing runs before you approve; change a stakeholder and you must approve again.</p>
        <div className="row"><label>Approved by<input value={by} onChange={(e) => setBy(e.target.value)} placeholder="Your name" /></label>
          <button disabled={!roles.length || !by.trim() || roles.some((r) => !r.name.trim() || !r.description.trim())} onClick={() => onApprove(by)}>Approve stakeholders</button></div>
        {approved && approval && <p className="ok" role="status">Locked: approved by {approval.approved_by} at {approval.approved_at}. Set fingerprint {approval.roles_hash.slice(0, 12)}…</p>}
        {!approved && approval && <p className="warn" role="status">Stakeholders changed since approval; approve again before running.</p>}
      </div>
      <div className="actions"><button className="secondary" onClick={onBack}>Back</button><button onClick={onNext}>Next: conditions</button></div>
    </section>)
}

// ---------------------------------------------------------------------------------------------------- Step 3
export function ConditionsStep({ roles, onNext, onBack, ...c }: Common & { roles: Role[]; onNext: () => void; onBack: () => void }) {
  const ro = c.readOnly  // the demo study's conditions are tied to its data
  const conds = c.study.conditions
  const setConds = (cs: PlanCondition[]) => c.update({ conditions: cs })
  const set = (i: number, p: Partial<PlanCondition>) => setConds(conds.map((x, k) => (k === i ? { ...x, ...p } : x)))
  const move = (i: number, d: number) => { const a = [...conds]; const j = i + d; if (j < 0 || j >= a.length) return; [a[i], a[j]] = [a[j], a[i]]; setConds(a) }
  const names = conds.map((x) => x.name.trim().toLowerCase()).filter(Boolean)
  const dup = names.length !== new Set(names).size
  const invalid = conds.filter((x) => x.name.trim() && !NAME_RE.test(x.name.trim())).map((x) => x.name)
  const ready = c.study.phenomenon.trim().length >= 20
  const template = () => {
    const header = ['case_id', ...conds.map((x) => x.name.trim()).filter(Boolean), c.study.outcome.name.trim()].filter(Boolean).join(',') + '\n'
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([header], { type: 'text/csv' })); a.download = 'data_template.csv'; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000)
  }
  return (
    <section aria-labelledby="s-cond">
      <h2 id="s-cond">Step 3: Conditions and outcome</h2>
      <p className="muted">Conditions are the factors that, alone or in combination, might bring about the outcome. fsQCA looks for combinations, so favour conditions that can work together or substitute for one another and that differ across your cases. List them yourself or ask for suggestions. You can refine them when you map your data in step 4.</p>
      <div className="card"><h3>Outcome: {c.study.outcome.name || '(not named)'}</h3><p className="muted">{c.study.outcome.description || 'No description yet; add one in step 1.'}</p></div>
      {ro && <p className="muted" role="note">These are the demo study's conditions; they are tied to its data and cannot be edited. Start a new study to plan your own.</p>}
      <AssistPanel kind="conditions" label="conditions" projectId={c.projectId} ai={c.ai} apiKey={c.apiKey} workspace={c.workspace} ready={ready} notReady="Describe your phenomenon and outcome in step 1 first."
        inputs={{ phenomenon: c.study.phenomenon, outcome: { name: c.study.outcome.name, description: c.study.outcome.description }, stakeholders: roles.map((r) => ({ name: r.name, description: r.description })), existing: conds.map((x) => ({ name: x.name, definition: x.definition })), count: 5 }}
        describe={(it) => ({ title: `${it.name} · ${it.calibration} · ${it.direction}`, body: `${it.definition} Measure: ${it.how_to_measure}` })}
        onAdd={(items, res) => setConds([...conds, ...items.map((it) => ({ name: it.name, definition: it.definition, how_to_measure: it.how_to_measure, calibration: it.calibration as Calibration, direction: it.direction as 'positive' | 'negative', rationale: it.rationale, ai: res.ai_generated }))])} />
      <div className="actions" style={{ justifyContent: 'flex-start' }}>
        <button className="secondary" disabled={ro} onClick={() => setConds([...conds, { name: '', definition: '', how_to_measure: '', calibration: 'direct', direction: 'positive' }])}>Add a condition yourself</button>
        <button className="secondary" disabled={!conds.length} onClick={template}>Download a blank data template (CSV)</button></div>
      {dup && <p className="warn" role="alert">Two conditions share a name; names must be unique.</p>}
      {invalid.length > 0 && <p className="warn" role="alert">Names must start with a letter and use only letters, digits and underscores: {invalid.join(', ')}.</p>}
      {conds.map((x, i) => (<div className="card" key={i}>
        <div className="row"><label>Name{x.ai && <> <span className="tag ai">AI-generated · editable</span></>}<input value={x.name} disabled={ro} onChange={(e) => set(i, { name: e.target.value })} aria-invalid={!!x.name.trim() && !NAME_RE.test(x.name.trim())} /></label>
          <label>How will it be calibrated?<select value={x.calibration} disabled={ro} onChange={(e) => set(i, { calibration: e.target.value as Calibration })}>
            <option value="direct">Raw measure, three anchors</option><option value="breakpoints">Raw measure, breakpoints (four-value)</option><option value="precalibrated">Already coded as memberships (0 to 1)</option></select></label>
          {x.calibration !== 'precalibrated' && <label>Direction<select value={x.direction} disabled={ro} onChange={(e) => set(i, { direction: e.target.value as 'positive' | 'negative' })}>
            <option value="positive">Positive (higher = more membership)</option><option value="negative">Negative (higher = less)</option></select></label>}</div>
        <label>Definition<textarea rows={2} value={x.definition} disabled={ro} onChange={(e) => set(i, { definition: e.target.value })} /></label>
        <label>{x.calibration === 'precalibrated' ? 'How the scores are assigned (coding rule)' : 'How it is measured'}<textarea rows={2} value={x.how_to_measure} disabled={ro} onChange={(e) => set(i, { how_to_measure: e.target.value })} /></label>
        {x.rationale && <p className="muted">Why it might matter (suggested): {x.rationale}</p>}
        <div className="actions" style={{ justifyContent: 'flex-start' }}>
          <button className="secondary" disabled={ro} onClick={() => move(i, -1)} aria-label={`Move ${x.name || 'condition'} up`}>↑</button>
          <button className="secondary" disabled={ro} onClick={() => move(i, 1)} aria-label={`Move ${x.name || 'condition'} down`}>↓</button>
          <button className="secondary" disabled={ro} onClick={() => setConds(conds.filter((_, k) => k !== i))}>Delete</button></div></div>))}
      <div className="actions"><button className="secondary" onClick={onBack}>Back</button><button disabled={dup || invalid.length > 0} onClick={onNext}>Next: your data</button></div>
    </section>)
}
