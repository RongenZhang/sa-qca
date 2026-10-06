import { useState } from 'react'
import { api, type AiSettings, type AssistInputs, type AssistKind, type AssistResult } from './api'

/** "Suggest ..." button with a visible preview of what will be sent, a labelled list of proposals, and explicit adding. */
export function AssistPanel({ kind, label, projectId, inputs, ai, apiKey, workspace, ready, notReady, describe, onAdd }: {
  kind: AssistKind; label: string; projectId: string; inputs: AssistInputs; ai: AiSettings; apiKey: string; workspace: string
  ready: boolean; notReady: string; describe: (item: Record<string, string>) => { title: string; body: string }; onAdd: (items: Record<string, string>[], result: AssistResult) => void
}) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [result, setResult] = useState<AssistResult | null>(null)
  const [picked, setPicked] = useState<Record<number, boolean>>({})
  const [preview, setPreview] = useState<{ prompt: string | null; scripted: boolean; sent: string } | null>(null)
  const body = { project_id: projectId, inputs, provider: ai.provider, model: ai.model, temperature: ai.temperature }

  const run = async () => {
    setBusy(true); setErr(''); setResult(null)
    try { const r = await api.assist(kind, body, apiKey, workspace); setResult(r); setPicked(Object.fromEntries(r.items.map((_, i) => [i, true]))) }
    catch (e) { setErr(String(e).replace(/^Error: /, '')) }
    setBusy(false)
  }
  const togglePreview = async (open: boolean) => { if (open && ready) { try { setPreview(await api.assistPreview(kind, body)) } catch (e) { setErr(String(e).replace(/^Error: /, '')) } } }
  const chosen = result ? result.items.filter((_, i) => picked[i]) : []

  return (
    <div className="card">
      <h3>Suggest {label}</h3>
      <p className="muted">{ai.provider === 'scripted' ? 'Scripted mode: no model is called.' : `Uses ${ai.model}.`} Suggestions are proposals you review, edit and add; nothing is added automatically.</p>
      <details onToggle={(e) => togglePreview((e.target as HTMLDetailsElement).open)}>
        <summary>What will be sent</summary>
        {preview ? <><p className="muted">{preview.sent}.</p>{preview.prompt && <pre tabIndex={0}>{preview.prompt}</pre>}</> : <p className="muted">{ready ? 'Loading…' : notReady}</p>}
      </details>
      <div className="actions" style={{ justifyContent: 'flex-start' }}><button disabled={busy || !ready} onClick={run}>{busy ? 'Asking…' : `Suggest ${label}`}</button>{!ready && <span className="muted">{notReady}</span>}</div>
      {err && <p role="alert" className="warn">{err}</p>}
      {result && <>
        <p role="status" className={result.ai_generated ? 'ai' : 'muted'}>{result.ai_generated ? <span className="tag ai">AI-generated · {result.provider}{result.model_id ? ` / ${result.model_id}` : ''} · editable</span> : <span className="tag">scripted, not language-model output</span>} {result.notice}</p>
        {result.items.length === 0 ? null : <>
          {result.items.map((it, i) => { const d = describe(it); return (
            <label key={i} className="card" style={{ display: 'block' }}><input type="checkbox" checked={!!picked[i]} onChange={(e) => setPicked({ ...picked, [i]: e.target.checked })} /> <b>{d.title}</b><br /><span className="muted">{d.body}</span></label>) })}
          <div className="actions" style={{ justifyContent: 'flex-start' }}>
            <button disabled={!chosen.length} onClick={() => { onAdd(chosen, result); setResult(null) }}>Add {chosen.length} selected to my list</button>
            <button className="secondary" onClick={() => setResult(null)}>Discard</button></div></>}</>}
    </div>)
}
