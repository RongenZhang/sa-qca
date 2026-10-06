import { useEffect, useState } from 'react'
import { api, type AiSettings, type Facts, type Narrative } from './api'

const pct = (x: number | null | undefined) => (x === null || x === undefined ? '–' : `${Math.round(100 * x)}%`)
const CLS: Record<string, string> = { robust: 'holds under every reading', contested: 'depends on the reading', 'stakeholder-specific': 'one reading only', 'analyst-only': 'only in your own solution', rare: 'rare' }
const SOURCE: Record<string, string> = { rules: 'Written by fixed rules from the computed facts.', ai: 'Drafted by a language model from the computed facts. Review it before you rely on it.', edited: 'Drafted from the computed facts and edited by you.' }

/** Step 8: what the solutions mean from each stakeholder's perspective. Facts are computed; the narrative is rules or an optional model draft. */
export function InterpretStep({ runId, ai, apiKey, workspace, demoOnly, onBack }: { runId: number | null; ai: AiSettings; apiKey: string; workspace: string; demoOnly: boolean; onBack: () => void }) {
  const [kind, setKind] = useState('parsimonious')
  const [policy, setPolicy] = useState('union')
  const [facts, setFacts] = useState<Facts | null>(null)
  const [rules, setRules] = useState<Narrative | null>(null)
  const [n, setN] = useState<Narrative | null>(null)
  const [source, setSource] = useState<'rules' | 'ai' | 'edited'>('rules')
  const [notes, setNotes] = useState('')
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [preview, setPreview] = useState<{ prompt: string | null; scripted: boolean; sent: string } | null>(null)
  const body = { kind, policy, provider: demoOnly ? 'scripted' : ai.provider, model: ai.model, temperature: ai.temperature }

  useEffect(() => {
    if (runId === null) return
    api.interpretation(runId, kind, policy).then((r) => {
      setFacts(r.facts); setRules(r.narrative); setErr('')
      if (r.saved && r.saved.kind === kind && r.saved.policy === policy) { setN(r.saved.narrative); setSource(r.saved.source); setNotes(r.saved.notes); setMsg(`Showing the version you saved at ${r.saved.saved_at}.`) }
      else { setN(r.narrative); setSource('rules'); setMsg('') }
    }).catch((e) => setErr(String(e).replace(/^Error: /, '')))
  }, [runId, kind, policy])

  if (runId === null) return <div className="card"><p>Run an analysis first (steps 5 and 6), then come back to interpret it.</p></div>
  const edit = (f: (d: Narrative) => void) => { setN((cur) => { if (!cur) return cur; const d = structuredClone(cur); f(d); return d }); setSource('edited') }
  const draftWithAi = async () => {
    setBusy(true); setErr(''); setMsg('')
    try { const r = await api.interpretationAi(runId, body, apiKey, workspace); setN(r.interpretation); setSource(r.ai_generated ? 'ai' : 'rules'); setMsg(r.notice || (r.ai_generated ? `Drafted by ${r.provider}${r.model_id ? ' / ' + r.model_id : ''}; every path and stakeholder was checked against the computed facts.` : '')) }
    catch (e) { setErr(String(e).replace(/^Error: /, '')) }
    setBusy(false)
  }
  const save = async () => { if (!n) return; setBusy(true); try { const r = await api.saveInterpretation(runId, { kind, policy, source, narrative: n, notes }); setMsg(`Saved at ${r.saved_at}. It will appear in your report and replication bundle.`); setErr('') } catch (e) { setErr(String(e).replace(/^Error: /, '')) } setBusy(false) }
  const stake = facts?.sources.filter((s) => s.kind === 'stakeholder' && s.n_valid > 0) ?? []

  return (
    <section aria-labelledby="s8">
      <h2 id="s8">Step 8: Interpretation from the stakeholder perspectives</h2>
      <p className="muted">What do the solutions mean once you take each stakeholder's reading seriously? First the facts, computed from the stored runs. Then an interpretation you can read, edit and save for your report.</p>
      <div className="card row"><label>Solution type<select value={kind} onChange={(e) => setKind(e.target.value)}><option>parsimonious</option><option>complex</option><option>intermediate</option></select></label>
        <label>Multiple models per solution<select value={policy} onChange={(e) => setPolicy(e.target.value)}><option value="union">union of all models' terms</option><option value="first">first model only</option></select></label></div>
      {err && <p role="alert" className="warn">{err}</p>}
      {facts && <>
        <div className="card"><h3>What the runs show</h3>
          <p className="muted">{facts.reference ? <>Your own solution ({facts.kind}): <b>{facts.reference.solution}</b>. </> : 'You gave no original calibration, so there is no analyst solution to compare with. '}
            {facts.agreement.n_stakeholders} stakeholder reading{facts.agreement.n_stakeholders === 1 ? '' : 's'}; within a reading, {pct(facts.agreement.within_reading_mean_modal_share)} of its runs agree on average; between readings, {pct(facts.agreement.between_readings_same_solution_share)} of pairs have the same typical solution.
            {facts.mechanical_matches_analyst_share !== null && <> The mechanical perturbation reproduced your solution in {pct(facts.mechanical_matches_analyst_share)} of its runs.</>}</p>
          <div style={{ overflowX: 'auto' }}><table><thead><tr><th>Path</th><th>Status</th>{stake.map((s) => <th key={s.id}>{s.label}</th>)}</tr></thead><tbody>
            {facts.paths.map((p) => <tr key={p.path}><td>{p.path}{!p.in_analyst_solution && <span className="muted"> (not in your solution)</span>}</td><td className={p.classification === 'robust' ? 'ok' : p.classification === 'analyst-only' ? 'warn' : ''}>{CLS[p.classification] ?? p.classification}</td>
              {stake.map((s) => <td key={s.id}>{pct(p.share_by_source[s.label])}</td>)}</tr>)}</tbody></table></div>
          <h3 style={{ marginTop: 14 }}>How each stakeholder calibrated, compared with you</h3>
          <div style={{ overflowX: 'auto' }}><table><thead><tr><th>Stakeholder</th><th>Typical solution</th><th>Stable?</th><th>Invalid</th><th>Compared with your calibration</th></tr></thead><tbody>
            {stake.map((s) => <tr key={s.id}><td>{s.label}</td><td>{s.modal_solution ?? 'none'}</td><td>{pct(s.modal_share)} of runs</td><td>{pct(s.invalid_rate)}</td>
              <td>{s.calibration.length ? s.calibration.map((c) => `${c.variable}: ${c.stance}${c.stance === 'similar' ? '' : ` (${c.shift_pct_of_scale > 0 ? '+' : ''}${c.shift_pct_of_scale}% of scale)`}`).join('; ') : '–'}</td></tr>)}</tbody></table></div></div>
        <div className="card"><h3>Interpretation</h3>
          <p role="status" className={source === 'ai' ? 'ai' : 'muted'}><span className={source === 'ai' ? 'tag ai' : 'tag'}>{source === 'ai' ? 'AI-drafted · editable' : source === 'edited' ? 'edited by you' : 'rule-based'}</span> {SOURCE[source]} {msg}</p>
          {n && !editing && <Narr n={n} />}
          {n && editing && <NarrEditor n={n} edit={edit} />}
          <div className="actions" style={{ justifyContent: 'flex-start' }}>
            <button className="secondary" onClick={() => setEditing((v) => !v)}>{editing ? 'Done editing' : 'Edit the text'}</button>
            <button className="secondary" onClick={() => { setN(rules); setSource('rules'); setMsg('') }}>Use the rule-based summary</button>
            <button className="secondary" disabled={busy} onClick={draftWithAi}>{busy ? 'Working…' : (demoOnly || ai.provider === 'scripted') ? 'Rewrite with the scripted summary' : `Draft with ${ai.model}`}</button></div>
          <details onToggle={async (e) => { if ((e.target as HTMLDetailsElement).open) { try { setPreview(await api.interpretationPreview(runId, body)) } catch (x) { setErr(String(x).replace(/^Error: /, '')) } } }}>
            <summary>What would be sent to a model</summary>{preview ? <><p className="muted">{preview.sent}.</p>{preview.prompt && <pre tabIndex={0}>{preview.prompt}</pre>}</> : <p className="muted">Loading…</p>}</details>
          <label>Your notes (appear in the report)<textarea rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="What you conclude, what you will check, who you will ask…" /></label>
          <div className="actions"><button className="secondary" onClick={onBack}>Back to results</button><button disabled={busy || !n} onClick={save}>Save as my interpretation</button></div></div></>}
    </section>)
}

function Narr({ n }: { n: Narrative }) {
  return (<div>
    <p><b>{n.headline}</b></p>
    {n.robust_findings.length > 0 && <><h4>What holds under every stakeholder reading</h4><ul>{n.robust_findings.map((f) => <li key={f.path}><b>{f.path}</b>: {f.meaning}</li>)}</ul></>}
    {n.contested_findings.length > 0 && <><h4>What depends on whose reading is used</h4><ul>{n.contested_findings.map((f) => <li key={f.path}><b>{f.path}</b> <span className="muted">(holds under: {f.holds_under.join(', ') || 'none'}; fails under: {f.fails_under.join(', ') || 'none'})</span>. {f.meaning}</li>)}</ul></>}
    <h4>Stakeholder by stakeholder</h4><ul>{n.stakeholder_perspectives.map((p) => <li key={p.stakeholder}><b>{p.stakeholder}</b>: {p.reading} <i>{p.implication}</i></li>)}</ul>
    <h4>Implications</h4><p>{n.implications}</p>
    <h4>Caveats</h4><ul>{n.caveats.map((c, i) => <li key={i}>{c}</li>)}</ul></div>)
}

function NarrEditor({ n, edit }: { n: Narrative; edit: (f: (d: Narrative) => void) => void }) {
  const ta = (label: string, value: string, set: (d: Narrative, v: string) => void, rows = 3) => <label key={label}>{label}<textarea rows={rows} value={value} onChange={(e) => edit((d) => set(d, e.target.value))} /></label>
  return (<div>
    {ta('Headline', n.headline, (d, v) => { d.headline = v }, 2)}
    {n.robust_findings.map((f, i) => ta(`Holds under every reading: ${f.path}`, f.meaning, (d, v) => { d.robust_findings[i].meaning = v }))}
    {n.contested_findings.map((f, i) => ta(`Depends on the reading: ${f.path}`, f.meaning, (d, v) => { d.contested_findings[i].meaning = v }))}
    {n.stakeholder_perspectives.map((p, i) => <div key={p.stakeholder}>{ta(`${p.stakeholder}: their reading`, p.reading, (d, v) => { d.stakeholder_perspectives[i].reading = v })}{ta(`${p.stakeholder}: what it implies`, p.implication, (d, v) => { d.stakeholder_perspectives[i].implication = v }, 2)}</div>)}
    {ta('Implications', n.implications, (d, v) => { d.implications = v }, 4)}
    {ta('Caveats (one per line)', n.caveats.join('\n'), (d, v) => { d.caveats = v.split('\n').filter((x) => x.trim()) }, 4)}
  </div>)
}
