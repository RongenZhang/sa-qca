import { useState } from 'react'
import { api, type Calibration, type ConfigureBody, type Demo, type UploadInfo } from './api'

type Col = { use: boolean; role: 'condition' | 'outcome'; cal: Calibration; direction: 'positive' | 'negative'; units: string; def: string; inst: string; dirExp: string; fn: string; cr: string; fm: string; b0: string; b33: string; b67: string }
const blank = (): Col => ({ use: false, role: 'condition', cal: 'direct', direction: 'positive', units: '', def: '', inst: '', dirExp: '', fn: '', cr: '', fm: '', b0: '', b33: '', b67: '' })
const num = (s: string) => (s.trim() === '' ? null : Number(s))

const str = (x: number | null | undefined) => (x === null || x === undefined ? '' : String(x))

export function Upload({ onReady, existing }: { onReady: (p: Demo) => void; existing?: { info: UploadInfo; config: ConfigureBody } }) {
  const ex = existing?.config
  const [info, setInfo] = useState<UploadInfo | null>(existing?.info ?? null)
  const [cols, setCols] = useState<Record<string, Col>>(() => {
    if (!existing) return {}
    return Object.fromEntries(existing.info.columns.map((c) => {
      const v = ex?.variables.find((x) => x.name === c.name)
      return [c.name, v ? { use: true, role: v.role as Col['role'], cal: v.calibration ?? 'direct', direction: v.direction as Col['direction'], units: v.units, def: v.construct_definition, inst: v.instrument, dirExp: str(v.dir_exp), fn: str(v.anchors?.full_non_membership), cr: str(v.anchors?.crossover), fm: str(v.anchors?.full_membership), b0: str(v.breakpoints?.break_0), b33: str(v.breakpoints?.break_33), b67: str(v.breakpoints?.break_67) } : blank()]
    }))
  })
  const [name, setName] = useState(ex?.name ?? '')
  const [desc, setDesc] = useState(ex?.case_description ?? '')
  const [drop, setDrop] = useState(ex?.drop_missing ?? false)
  const [cons, setCons] = useState(str(ex?.reference_cutoffs?.consistency_threshold))
  const [freq, setFreq] = useState(str(ex?.reference_cutoffs?.frequency_threshold))
  const [pri, setPri] = useState(str(ex?.reference_cutoffs?.pri_threshold))
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (n: string, p: Partial<Col>) => setCols((c) => ({ ...c, [n]: { ...c[n], ...p } }))

  const pick = async (f: File | undefined) => {
    if (!f) return
    setErr(''); setBusy(true)
    try { const u = await api.upload(f); setInfo(u); setName(f.name.replace(/\.[^.]+$/, '')); setCols(Object.fromEntries(u.columns.map((c) => [c.name, blank()]))) } catch (e) { setErr(String(e).replace(/^Error: /, '')); setInfo(null) }
    setBusy(false)
  }
  const used = info ? info.columns.filter((c) => cols[c.name]?.use) : []
  const missing = used.reduce((a, c) => a + c.n_missing, 0)
  const save = async () => {
    if (!info) return
    setErr(''); setBusy(true)
    const body: ConfigureBody = {
      name, case_description: desc, drop_missing: drop,
      reference_cutoffs: cons || freq ? { consistency_threshold: num(cons), frequency_threshold: num(freq), pri_threshold: num(pri) } : null,
      variables: used.map((c) => { const v = cols[c.name]; const a = { full_non_membership: num(v.fn), crossover: num(v.cr), full_membership: num(v.fm) }; const b = { break_0: num(v.b0), break_33: num(v.b33), break_67: num(v.b67) }
        return { name: c.name, role: v.role, direction: v.cal === 'precalibrated' ? 'positive' : v.direction, calibration: v.cal, construct_definition: v.def, instrument: v.inst, units: v.units, dir_exp: v.role === 'condition' && v.dirExp !== '' ? Number(v.dirExp) : null,
          anchors: v.cal === 'direct' && (v.fn || v.cr || v.fm) ? a : null, breakpoints: v.cal === 'breakpoints' && (v.b0 || v.b33 || v.b67) ? b : null } }),
    }
    try { onReady(await api.configure(info.project_id, body)) } catch (e) { setErr(String(e).replace(/^Error: /, '')) }
    setBusy(false)
  }
  return (
    <div className="card">
      <h3>{existing ? 'Edit project' : 'Upload your data'}</h3>
      {existing && <p className="muted" role="note">Edits apply to future runs and prompts. Runs you have already made keep the definitions they used.</p>}
      <p className="muted">CSV (comma, semicolon or tab) or Excel (first sheet), up to 10 MB. The file stays on this machine. Only definitions and summary statistics of the variables you choose are ever sent to a model.</p>
      {!existing && <label>Data file<input type="file" accept=".csv,.tsv,.txt,.xlsx,.xlsm" onChange={(e) => pick(e.target.files?.[0])} /></label>}
      {err && <p role="alert" className="warn">{err}</p>}
      {info && <>
        <p><b>{info.filename}</b> · {info.n_rows} rows · {info.columns.length} columns</p>
        <div style={{ overflowX: 'auto' }}><table><thead><tr>{info.preview.header.map((h) => <th key={h}>{h}</th>)}</tr></thead><tbody>
          {info.preview.rows.map((r, i) => <tr key={i}>{r.map((c, k) => <td key={k}>{c ?? <span className="muted">(missing)</span>}</td>)}</tr>)}</tbody></table></div>
        <div className="row"><label>Project name<input value={name} onChange={(e) => setName(e.target.value)} /></label></div>
        <label>Phenomenon and cases (paste from your article)<textarea rows={7} value={desc} onChange={(e) => setDesc(e.target.value)} /></label>
        <p className="muted">This text is the context every agent reads, and the basis for choosing stakeholder roles. Describe who or what the cases are, the setting and period, how the outcome shows up in practice, and what the decision or process involves. Do <b>not</b> include your findings, hypotheses or which combinations matter: the agents should not know the answer. ({desc.trim().length} characters; a few paragraphs works best.)</p>
        <h3 style={{ marginTop: 14 }}>Choose the outcome and conditions</h3>
        <p className="muted">Columns such as case names or IDs are simply left unticked. Give each chosen variable its construct definition and measurement instrument: without them an agent only sees numbers and tends to return a percentile rule. Original anchors and cutoffs are optional, but the mechanical source and the comparison with your published solution need them.</p>
        {info.columns.map((c) => { const v = cols[c.name]; if (!v) return null
          return (<div className="card" key={c.name}>
            <label style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}><input type="checkbox" disabled={!c.numeric} checked={v.use} onChange={(e) => set(c.name, { use: e.target.checked })} /> <b>{c.name}</b>
              {!c.numeric && <span className="muted">not numeric, cannot be used</span>}{c.n_missing > 0 && <span className="warn">{c.n_missing} missing</span>}</label>
            {v.use && <>
              <div className="row"><label>Role<select value={v.role} onChange={(e) => set(c.name, { role: e.target.value as Col['role'], ...(e.target.value === 'outcome' && v.cal === 'precalibrated' ? { cal: 'direct' as Calibration } : {}) })}><option value="condition">Condition</option><option value="outcome">Outcome</option></select></label>
                <label>How is it calibrated?<select value={v.cal} onChange={(e) => set(c.name, { cal: e.target.value as Calibration })}>
                  <option value="direct">Raw measure, three anchors (direct, logistic)</option>
                  <option value="breakpoints">Raw measure, breakpoints (four-value scale 0 / 0.33 / 0.67 / 1)</option>
                  {v.role === 'condition' && <option value="precalibrated">Already calibrated (0 to 1): use as given</option>}</select></label>
                {v.cal !== 'precalibrated' && <label>Direction<select value={v.direction} onChange={(e) => set(c.name, { direction: e.target.value as Col['direction'] })}><option value="positive">Positive (higher raw value = more membership)</option><option value="negative">Negative (higher raw value = less membership)</option></select></label>}
                <label>Units<input value={v.units} onChange={(e) => set(c.name, { units: e.target.value })} /></label>
                {v.role === 'condition' && <label>Directional expectation<select value={v.dirExp} onChange={(e) => set(c.name, { dirExp: e.target.value })}><option value="">none</option><option value="1">presence contributes</option><option value="0">absence contributes</option></select></label>}</div>
              {v.cal === 'precalibrated' && <p className="muted" role="note">These values are taken exactly as they are. Agents are not asked to calibrate this variable, and it stays fixed across all sources.</p>}
              <label>Construct definition<textarea rows={2} value={v.def} onChange={(e) => set(c.name, { def: e.target.value })} /></label>
              <label>{v.cal === 'precalibrated' ? 'How the scores were assigned (coding rule, rubric)' : 'Measurement instrument (item wording, scale, scale anchors)'}<textarea rows={2} value={v.inst} onChange={(e) => set(c.name, { inst: e.target.value })} /></label>
              {v.cal === 'direct' && <div className="row"><label>Original full non-membership<input inputMode="decimal" value={v.fn} onChange={(e) => set(c.name, { fn: e.target.value })} /></label>
                <label>Original crossover<input inputMode="decimal" value={v.cr} onChange={(e) => set(c.name, { cr: e.target.value })} /></label>
                <label>Original full membership<input inputMode="decimal" value={v.fm} onChange={(e) => set(c.name, { fm: e.target.value })} /></label></div>}
              {v.cal === 'breakpoints' && <><div className="row"><label>Original break_0 (boundary between 0 and 0.33)<input inputMode="decimal" value={v.b0} onChange={(e) => set(c.name, { b0: e.target.value })} /></label>
                <label>Original break_33 (0.33 and 0.67)<input inputMode="decimal" value={v.b33} onChange={(e) => set(c.name, { b33: e.target.value })} /></label>
                <label>Original break_67 (0.67 and 1)<input inputMode="decimal" value={v.b67} onChange={(e) => set(c.name, { b67: e.target.value })} /></label></div>
                <p className="muted">A value exactly on a boundary takes the lower of the two scores. For a negative direction the boundaries run from high to low values.</p></>}
</>}
          </div>) })}
        <div className="card"><h3>Your original truth-table cutoffs (optional)</h3><div className="row">
          <label>Consistency (0–1)<input inputMode="decimal" value={cons} onChange={(e) => setCons(e.target.value)} /></label>
          <label>Frequency (cases, ≥ 1)<input inputMode="numeric" value={freq} onChange={(e) => setFreq(e.target.value)} /></label>
          <label>PRI (optional)<input inputMode="decimal" value={pri} onChange={(e) => setPri(e.target.value)} /></label></div></div>
        {missing > 0 && <label><input type="checkbox" checked={drop} onChange={(e) => setDrop(e.target.checked)} /> Drop rows with missing values in the chosen columns (listwise deletion; QCA needs complete data). The number dropped is recorded.</label>}
        <div className="actions"><span /><button disabled={busy || used.length < 3} onClick={save}>{existing ? 'Save changes' : 'Save project'}</button></div></>}
    </div>)
}
