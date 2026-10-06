import type { AiSettings } from './api'

export const DEFAULT_AI: AiSettings = { provider: 'scripted', model: 'claude-opus-5-5', temperature: null }

/** One place to choose how the tool gets help from a model. The key and workspace ID live only in this tab's memory. */
export function AiSettingsPanel({ ai, setAi, apiKey, setApiKey, workspace, setWorkspace, demoOnly, onClose }: {
  ai: AiSettings; setAi: (a: AiSettings) => void; apiKey: string; setApiKey: (k: string) => void; workspace: string; setWorkspace: (w: string) => void; demoOnly: boolean; onClose: () => void
}) {
  return (
    <section className="card" aria-labelledby="ai-h">
      <h2 id="ai-h">AI settings</h2>
      <p className="muted">Used by the suggestion helpers (stakeholders, conditions, interpretation) and by the calibration runs. Choose "Scripted" to work without any model.</p>
      <div className="row">
        <label>Model provider<select value={demoOnly ? 'scripted' : ai.provider} disabled={demoOnly} onChange={(e) => setAi({ ...ai, provider: e.target.value as AiSettings['provider'] })}>
          <option value="scripted">Scripted (no model is called)</option>{!demoOnly && <option value="anthropic">Anthropic</option>}</select></label>
        {ai.provider === 'anthropic' && !demoOnly && <>
          <label>Model<input value={ai.model} onChange={(e) => setAi({ ...ai, model: e.target.value })} /></label>
          <label>Temperature (blank = provider default)<input type="number" step="0.1" value={ai.temperature ?? ''} onChange={(e) => setAi({ ...ai, temperature: e.target.value === '' ? null : +e.target.value })} /></label></>}
      </div>
      {ai.provider === 'anthropic' && !demoOnly && <div className="row">
        <label>API key (kept in this tab's memory only; sent with each request)<input type="password" autoComplete="off" value={apiKey} onChange={(e) => setApiKey(e.target.value)} /></label>
        <label>Workspace ID (only if the provider says your key is not scoped to a workspace)<input autoComplete="off" value={workspace} onChange={(e) => setWorkspace(e.target.value)} placeholder="wrkspc_…" /></label></div>}
      <p className="muted"><b>What a model sees.</b> The planning helpers see only the text you wrote in the steps. The calibration runs see definitions, instruments and summary statistics of each variable. A model never sees your data rows, and everything it returns is shown to you, editable, and labelled as AI-generated.</p>
      {demoOnly && <p className="muted" role="note">This public demo never calls a model.</p>}
      <div className="actions"><span /><button onClick={onClose}>Done</button></div>
    </section>)
}
