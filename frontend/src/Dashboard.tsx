import { useEffect, useMemo, useState } from 'react'
import { getSid, withSid } from './api'
import { api2, type Attempt, type Dashboard as D, type Demo, type Rationale, type Results } from './api'
import { AnchorStrip, armColors, RobustnessHeat, SimilarityBox } from './charts'
import { ChartFrame } from './export'
import { sourceLabel } from './labels'

const TABS = ['Solutions', 'Robustness', 'Similarity', 'Anchors', 'Rationales', 'Validation'] as const
type Tab = (typeof TABS)[number]
function ExportCard({ id }: { id: number }) {
  const [v, setV] = useState<Record<string, unknown> | 'busy' | null>(null)
  const verify = async () => {
    setV('busy')
    const h = { 'X-Session': getSid() }
    try {
      const r = await fetch(`/api/runs/${id}/verify`, { method: 'POST', headers: h })
      if (!r.ok) { setV({ ok: false, error: (await r.json().catch(() => ({}))).detail ?? r.statusText }); return }
      for (let i = 0; i < 300; i++) {  // the check re-runs R and can take minutes: poll
        await new Promise((res) => setTimeout(res, 2000))
        const st = await (await fetch(`/api/runs/${id}/verify`, { headers: h })).json()
        if (st.state === 'done') { setV(st.result); return }
      }
      setV({ ok: false, error: 'verification is taking too long; try again later' })
    } catch (e) { setV({ ok: false, error: String(e) }) }
  }
  const r = typeof v === 'object' && v ? v : null
  return (<div className="card"><h3>Export and verify</h3>
    <p className="muted">The bundle contains the data, prompts, raw responses, decisions, R code and checksums, and no API keys. The report is HTML: use your browser's Print to save a PDF.</p>
    <div className="actions" style={{ justifyContent: 'flex-start' }}>
      <a href={withSid(`/api/runs/${id}/bundle`)}><button>Download replication bundle (ZIP)</button></a>
      <a href={withSid(`/api/runs/${id}/report`)} target="_blank" rel="noreferrer"><button className="secondary">Open report (HTML)</button></a>
      <button className="secondary" disabled={v === 'busy'} onClick={verify}>{v === 'busy' ? 'Re-running R…' : 'Verify bundle'}</button></div>
    {r && <p role="status" className={r.ok ? 'ok' : 'warn'}>{r.ok ? `Verified: ${r.n_match} of ${r.n_runs} runs reproduced exactly; ${r.n_files} files match the manifest.` : `Not verified: ${String(r.error ?? '')} ${r.n_mismatch ? `${r.n_mismatch} run(s) differ.` : ''}`}</p>}
  </div>)
}
function solutionCounts(d: D): { source: string; solution: string; runs: number; similarity: number | null }[] {
  const score = new Map(d.similarity.map((x) => [x.run_id, x.score]))
  const g = new Map<string, { source: string; solution: string; runs: number; similarity: number | null }>()
  for (const m of d.matrix) {
    if (m.solution === null) continue
    const k = m.arm + '\u0000' + m.solution
    const cur = g.get(k) ?? { source: m.arm, solution: m.solution, runs: 0, similarity: score.get(m.run_id) ?? null }
    cur.runs += 1
    g.set(k, cur)
  }
  return [...g.values()].sort((a, b) => a.source.localeCompare(b.source) || b.runs - a.runs)
}
const pct = (v: number | null) => (v === null ? '–' : `${(v * 100).toFixed(0)}%`)

export function Dashboard({ results, demo }: { results: Results; demo: Demo }) {
  const [tab, setTab] = useState<Tab>('Solutions')
  const [kind, setKind] = useState('parsimonious')
  const [metric, setMetric] = useState('jaccard_terms')
  const [policy, setPolicy] = useState('union')
  const [metrics, setMetrics] = useState<Record<string, string>>({})
  const [d, setD] = useState<D | null>(null)
  const [err, setErr] = useState('')
  const id = results.config.id
  useEffect(() => { api2.metrics().then(setMetrics).catch(() => undefined) }, [])
  useEffect(() => { api2.dashboard(id, kind, metric, policy).then((x) => { setD(x); setErr('') }).catch((e) => setErr(String(e))) }, [id, kind, metric, policy])
  const arms = useMemo(() => d?.arms ?? [], [d])
  const colors = useMemo(() => armColors(arms), [arms])
  return (
    <section aria-labelledby="s5"><h2 id="s5">Step 5: Results dashboard</h2><p className="muted">Compare what each source finds with your original solution.</p>
      <p className="muted">Run #{id} · {results.config.provider}/{results.config.model} · template {results.config.template_version}. Every number traces to a stored run (run ids shown). The analyst's original specification is run through the identical pipeline as the reference.</p>
      <div className="card row">
        <label>Solution type<select value={kind} onChange={(e) => setKind(e.target.value)}><option>parsimonious</option><option>complex</option><option>intermediate</option></select></label>
        <label>Multiple models per solution<select value={policy} onChange={(e) => setPolicy(e.target.value)}><option value="union">union of all models' terms</option><option value="first">first model only</option></select></label>
        <label>Similarity metric<select value={metric} onChange={(e) => setMetric(e.target.value)}>{Object.keys(metrics).map((m) => <option key={m}>{m}</option>)}</select></label>
      </div>
      <ExportCard id={id} />
      {d && <p className="muted">Metric: {d.metric_doc} Analyst reference solution ({d.kind}): <b>{d.reference_solution ?? 'unavailable'}</b></p>}
      {err && <p role="alert" className="warn">{err}</p>}
      <div role="tablist" aria-label="Dashboard views" className="steps">{TABS.map((t) => <span key={t} className={t === tab ? 'cur' : ''}><button role="tab" aria-selected={t === tab} onClick={() => setTab(t)}>{t}</button></span>)}</div>
      {d && tab === 'Solutions' && <>
        <ChartFrame title="Solution matrix (sources × runs)" data={d.matrix.map((m) => ({ ...m }))} note="Each row is one stored run. Invalid runs have no solution.">
          <table><thead><tr><th>Source</th><th>Run</th><th>Status</th><th>Solution</th></tr></thead><tbody>
            {d.matrix.map((m) => <tr key={m.run_id}><td>{sourceLabel(m.arm)}</td><td>{m.rep} <span className="muted">(#{m.run_id})</span></td><td className={m.status === 'invalid' ? 'warn' : ''}>{m.status}</td><td>{m.solution ?? '–'}</td></tr>)}</tbody></table></ChartFrame>
        <ChartFrame title="Path frequency by source" data={d.path_frequency.map((p) => ({ path: p.path, ...p.counts }))} note="How often each configuration appears, per source (count of valid runs).">
          <table><thead><tr><th>Path</th>{arms.map((a) => <th key={a}>{sourceLabel(a)}</th>)}</tr></thead><tbody>
            {d.path_frequency.map((p) => <tr key={p.path}><td>{p.path}</td>{arms.map((a) => <td key={a}>{p.counts[a] ?? 0}/{d.valid_runs[a]}</td>)}</tr>)}</tbody></table></ChartFrame></>}
      {d && tab === 'Robustness' && <>
        <ChartFrame title="Robustness of the analyst's paths" data={d.robustness.map((r) => ({ path: r.path, across_roles: r.across_roles, ...r.share_by_arm }))} note="Share of valid runs, per source, whose solution contains each path of the analyst's original solution.">
          {d.robustness.length ? <RobustnessHeat rows={d.robustness} arms={arms} /> : <p>No reference solution to evaluate.</p>}</ChartFrame>
        <ul>{d.robustness.map((r) => <li key={r.path}><b>{r.path}</b>: {r.across_roles === 'all roles' ? 'appears under every stakeholder reading' : r.across_roles === 'one role only' ? 'appears under only one stakeholder reading' : r.across_roles}</li>)}</ul></>}
      {d && tab === 'Similarity' && <>
        <div className="card"><h3>How to read this</h3>
          <p>Each run applies one set of anchors and cutoffs and produces a QCA solution. The score runs from 0 to 1: <b>1 means the run found the same solution as the analyst's, and 0 means the two solutions share no terms</b> (Jaccard similarity over solution terms; metric: {d.metric}). Each circle stands for all runs with the same score, and the number inside it shows how many runs that is. A source whose runs all land at 1 agrees with the analyst; a source with circles lower down reads the measure differently enough to change the finding.</p></div>
        <ChartFrame title="Similarity to the analyst's solution" data={d.similarity.map((s) => ({ ...s, distinct_solutions_in_source: d.distinct_solutions[s.arm] }))} note="One row of the CSV per run.">
          {d.reference_solution ? <SimilarityBox data={d.similarity} arms={arms} colors={colors} distinct={d.distinct_solutions} /> : <p>No reference solution.</p>}</ChartFrame>
        <ChartFrame title="Which solutions each source produced" data={solutionCounts(d).map((r) => ({ ...r }))} note="Runs per source, grouped by the solution they produced.">
          <table><thead><tr><th>Source</th><th>Solution</th><th>Runs</th><th>Similarity</th></tr></thead><tbody>
            {solutionCounts(d).map((r, i) => <tr key={i}><td>{sourceLabel(r.source)}</td><td>{r.solution}</td><td>{r.runs}</td><td>{r.similarity === null ? '–' : r.similarity.toFixed(2)}</td></tr>)}</tbody></table></ChartFrame></>}
      {tab === 'Anchors' && demo.variables.map((v) => <ChartFrame key={v.name} title={`Anchors: ${v.name}`} data={results.runs.filter((r) => r.anchors).map((r) => ({ run_id: r.run_id, arm: r.arm, variable: v.name, ...(v.role === 'outcome' ? r.anchors!.outcome ?? r.anchors![v.name] : r.anchors![v.name]) }))} note="Proposed anchors per source, over the observed distribution.">
        <AnchorStrip variable={v.name} stats={v.stats} reference={demo.reference[v.name]} arms={arms} colors={colors}
          rows={results.runs.filter((r) => r.anchors && r.arm !== 'reference').map((r) => ({ arm: r.arm, run_id: r.run_id, a: (r.anchors![v.name] ?? r.anchors!.outcome) as Record<string, number> }))} /></ChartFrame>)}
      {tab === 'Rationales' && <RationaleBrowser id={id} arms={arms} demo={demo} />}
      {tab === 'Validation' && <ChartFrame title="Validation report" data={Object.entries(results.report).map(([arm, r]) => ({ arm, runs: r.n_runs, invalid_rate: r.invalid_rate, first_attempt_failure_rate: r.first_attempt_failure_rate, statuses: JSON.stringify(r.status_counts), reasons: JSON.stringify(r.failure_reasons) }))} note="Invalid judgments are results, not noise: a second validation failure is recorded and never repaired.">
        <table><thead><tr><th>Source</th><th>Runs</th><th>Invalid rate</th><th>First-attempt failure</th><th>Statuses</th><th>Failure reasons</th></tr></thead><tbody>
          {Object.entries(results.report).map(([arm, r]) => <tr key={arm}><td>{sourceLabel(arm)}</td><td>{r.n_runs}</td><td>{pct(r.invalid_rate)}</td><td>{pct(r.first_attempt_failure_rate)}</td><td>{Object.entries(r.status_counts).map(([k, v]) => `${k}: ${v}`).join(', ')}</td><td>{Object.entries(r.failure_reasons).map(([k, v]) => `${k}: ${v}`).join(', ') || '–'}</td></tr>)}</tbody></table></ChartFrame>}
    </section>)
}

function RationaleBrowser({ id, arms, demo }: { id: number; arms: string[]; demo: Demo }) {
  const [arm, setArm] = useState('')
  const [variable, setVariable] = useState('')
  const [rows, setRows] = useState<Rationale[]>([])
  const [open, setOpen] = useState<Record<number, Attempt | 'loading'>>({})
  useEffect(() => { api2.rationales(id, arm, variable).then(setRows).catch(() => setRows([])) }, [id, arm, variable])
  const show = async (aid: number) => { setOpen((o) => ({ ...o, [aid]: 'loading' })); const a = await api2.attempt(aid); setOpen((o) => ({ ...o, [aid]: a })) }
  return (<>
    <div className="card row"><label>Source<select value={arm} onChange={(e) => setArm(e.target.value)}><option value="">all</option>{['reference', ...arms].map((a) => <option key={a} value={a}>{sourceLabel(a)}</option>)}</select></label>
      <label>Variable<select value={variable} onChange={(e) => setVariable(e.target.value)}><option value="">all</option>{demo.variables.map((v) => <option key={v.name}>{v.name}</option>)}</select></label></div>
    <ChartFrame title="Rationales" data={rows.map((r) => ({ ...r }))} note={`${rows.length} rationales. Agent rationales link to the exact prompt and raw response.`}>
      <table><thead><tr><th>Source</th><th>Run</th><th>Variable · anchor</th><th>Value</th><th>Rationale</th></tr></thead><tbody>
        {rows.slice(0, 200).map((r, i) => <tr key={i}><td>{sourceLabel(r.arm)}</td><td>#{r.run_id}</td><td>{r.variable} · {r.anchor}</td><td>{r.value}</td>
          <td>{r.rationale}{r.attempt_id && <><br /><button className="secondary" onClick={() => show(r.attempt_id!)}>Prompt & raw response</button>
            {typeof open[r.attempt_id] === 'object' && (() => { const a = open[r.attempt_id!] as Attempt; return <details open><summary>Attempt #{a.id} ({a.kind}) · {a.model_id} · prompt sha256 {a.prompt_sha256.slice(0, 12)}…</summary><pre tabIndex={0}>{a.rendered_prompt}</pre><pre tabIndex={0}>{a.raw_response}</pre></details> })()}</>}</td></tr>)}</tbody></table></ChartFrame></>)
}
