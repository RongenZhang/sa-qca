export type Stats = { n: number; min: number; q1: number; median: number; q3: number; max: number; mean: number; histogram: { lower: number; upper: number; count: number }[] }
export type Calibration = 'direct' | 'breakpoints' | 'precalibrated'
export type Variable = { calibration: Calibration; name: string; role: 'condition' | 'outcome'; direction: string; construct_definition: string; instrument: string; units: string; stats: Stats }
export type Demo = { id: string; is_demo: boolean; has_reference: boolean; n_dropped: number; name: string; case_description: string; variables: Variable[]; reference: Record<string, Record<string, number>>; reference_cutoffs: Record<string, number | null>; dir_exp: Record<string, number | null>; warnings: string[]; n_cases: number }
export type UploadInfo = { project_id: string; filename: string; n_rows: number; columns: { name: string; numeric: boolean; n_missing: number; n_unique: number }[]; preview: { header: string[]; rows: (string | null)[][] } }
export type ConfigureBody = { name: string; case_description: string; drop_missing: boolean; reference_cutoffs: Record<string, number | null> | null; variables: { name: string; role: string; direction: string; calibration: Calibration; construct_definition: string; instrument: string; units: string; dir_exp: number | null; anchors: Record<string, number | null> | null; breakpoints: Record<string, number | null> | null }[] }
export type PlanCondition = { name: string; definition: string; how_to_measure: string; calibration: Calibration; direction: 'positive' | 'negative'; rationale?: string; ai?: boolean }
export type Study = { phenomenon: string; outcome: { name: string; description: string; how_to_measure?: string; calibration?: Calibration; direction?: 'positive' | 'negative' }; stakeholders: Role[]; conditions: PlanCondition[] }
export type StudyState = { study: Study; has_dataset: boolean; configured: boolean; name: string; read_only: boolean }
export type StudyListItem = { id: string; name: string; created_at: string; has_dataset: boolean; configured: boolean; outcome: string }
export type AssistKind = 'stakeholders' | 'conditions'
export type AssistInputs = { phenomenon: string; outcome: { name: string; description: string }; existing?: unknown[]; stakeholders?: unknown[]; count?: number }
export type AssistResult = { items: Record<string, string>[]; generic: boolean; notice: string; provider: string; model_id: string | null; ai_generated: boolean; helper_call_ids: number[] }
export type AiSettings = { provider: 'scripted' | 'anthropic'; model: string; temperature: number | null }
export type Narrative = { headline: string; robust_findings: { path: string; meaning: string }[]; contested_findings: { path: string; holds_under: string[]; fails_under: string[]; meaning: string }[]
  stakeholder_perspectives: { stakeholder: string; reading: string; implication: string }[]; implications: string; caveats: string[] }
export type Facts = {
  kind: string; reference: { solution: string; paths: string[] } | null; scripted: boolean
  sources: { id: string; label: string; kind: string; n_runs: number; n_valid: number; n_invalid: number; invalid_rate: number | null; modal_solution: string | null; modal_share: number | null
    distinct_solutions: number; similarity_to_analyst_mean: number | null; matches_analyst_share: number | null; calibration: { variable: string; stance: string; shift_pct_of_scale: number }[] }[]
  paths: { path: string; in_analyst_solution: boolean; classification: string; present_under: string[]; absent_under: string[]; share_by_source: Record<string, number>; calibration_contrast: { variable: string; shift_where_absent: number; shift_where_present: number }[] }[]
  agreement: { n_stakeholders: number; within_reading_mean_modal_share: number | null; between_readings_same_solution_share: number | null; between_readings_mean_similarity: number | null }
  mechanical_matches_analyst_share: number | null
}
export type SavedInterpretation = { kind: string; policy: string; source: 'rules' | 'ai' | 'edited'; narrative: Narrative; notes: string; saved_at: string }
export type Role = { name: string; description: string; relevance: string; ai?: boolean }
export type RunReq = { project_id: string; role_set_hash: string; arms: { roles: string[]; generic: boolean; mechanical: boolean }; reps: number; provider: string; model: string; temperature: number | null; tolerance: number; spend_cap: number | null; price_in: number | null; price_out: number | null }
export type RunRow = { run_id: number; arm: string; rep: number; status: string; mechanical_id: string | null; attempts: number; anchors: Record<string, Record<string, number>> | null; solutions: Record<'complex' | 'parsimonious' | 'intermediate', string[][]> | null }
export type ArmReport = { n_runs: number; status_counts: Record<string, number>; invalid_rate: number | null; first_attempt_failure_rate: number | null; failure_reasons: Record<string, number> }
export type Status = { provider_errors?: string[]; state: string; total: number; done: number; status_counts: Record<string, number>; report: Record<string, ArmReport> }
export type Results = { config: { id: number; project_id: string; model: string; provider: string; template_version: string; reps: number; arms: string[] }; runs: RunRow[]; report: Record<string, ArmReport>; project: Demo }

/** Per-browser capability token: only this browser can read the runs it started. Kept in localStorage when available. */
let memSid = ''
export function getSid(): string {
  try { let s = localStorage.getItem('saqca.sid'); if (!s) { s = crypto.randomUUID().replace(/-/g, '') + 'x'; localStorage.setItem('saqca.sid', s) } return s } catch { if (!memSid) memSid = crypto.randomUUID().replace(/-/g, '') + 'x'; return memSid }
}
export const withSid = (url: string) => url + (url.includes('?') ? '&' : '?') + 'sid=' + getSid()

async function j<T>(path: string, body?: unknown, headers: Record<string, string> = {}): Promise<T> {
  headers = { 'X-Session': getSid(), ...headers }
  const r = await fetch(path, body === undefined ? { headers } : { method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) })
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail ?? r.statusText)
  return r.json()
}
export const api = {
  studies: () => j<StudyListItem[]>('/api/studies'),
  newStudy: (name: string) => j<{ project_id: string }>('/api/studies', { name }),
  getStudy: (pid: string) => j<StudyState>(`/api/projects/${pid}/study`),
  putStudy: async (pid: string, study: Study, name?: string): Promise<StudyState> => {
    const r = await fetch(`/api/projects/${pid}/study`, { method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-Session': getSid() }, body: JSON.stringify({ study, name }) })
    if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail ?? r.statusText)
    return r.json()
  },
  attach: async (pid: string, file: File) => {
    const fd = new FormData(); fd.append('file', file)
    const r = await fetch(`/api/projects/${pid}/dataset`, { method: 'POST', body: fd, headers: { 'X-Session': getSid() } })
    if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail ?? r.statusText)
    return r.json() as Promise<UploadInfo>
  },
  assist: (kind: AssistKind, body: { project_id: string; inputs: AssistInputs; provider: string; model: string; temperature: number | null }, key: string, workspace: string) =>
    j<AssistResult>(`/api/assist/${kind}`, body, { ...(key ? { 'X-Provider-Key': key } : {}), ...(workspace ? { 'X-Provider-Workspace': workspace } : {}) }),
  assistPreview: (kind: AssistKind, body: { project_id: string; inputs: AssistInputs; provider: string; model: string; temperature: number | null }) =>
    j<{ prompt: string | null; scripted: boolean; sent: string }>(`/api/assist/${kind}/preview`, body),
  project: (pid: string) => j<Demo>(`/api/projects/${pid}`),
  mode: () => j<{ mode: 'demo' | 'full'; max_reps: number; max_roles: number; retention_hours: number }>('/api/mode'),
  upload: async (file: File) => {
    const fd = new FormData(); fd.append('file', file)
    const r = await fetch('/api/projects/upload', { method: 'POST', body: fd, headers: { 'X-Session': getSid() } })
    if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail ?? r.statusText)
    return r.json() as Promise<UploadInfo>
  },
  setup: (pid: string) => j<{ upload: UploadInfo; config: ConfigureBody | null; study: Study; draft_config?: ConfigureBody & { unmatched_plan?: string[] } }>(`/api/projects/${pid}/setup`),
  configure: (pid: string, body: ConfigureBody) => j<Demo>(`/api/projects/${pid}/configure`, body),
  suggest: () => j<{ ai_generated: boolean; roles: Role[] }>('/api/roles/suggest', {}),
  approve: (roles: Role[], approved_by: string) => j<{ roles_hash: string; approved_by: string; approved_at: string }>('/api/roles/approve', { roles, approved_by }),
  preview: (role: Role | null, project_id: string) => j<{ prompt: string; sent_to_provider: string; warnings: string[]; template_version: string }>('/api/prompt/preview', { role, project_id }),
  estimate: (req: RunReq) => j<{ llm_calls_min: number; llm_calls_max: number; mechanical_runs: number; approx_input_tokens_per_call: number; approx_output_tokens_per_call: number; cost_usd_max: number | null }>('/api/runs/estimate', req),
  start: (req: RunReq, key: string, workspace = '') => j<{ run_config_id: number }>('/api/runs', req, { ...(key ? { 'X-Provider-Key': key } : {}), ...(workspace ? { 'X-Provider-Workspace': workspace } : {}) }),
  cancel: (id: number) => j<unknown>(`/api/runs/${id}/cancel`, {}),
  interpretation: (id: number, kind: string, policy: string) => j<{ facts: Facts; narrative: Narrative; saved: SavedInterpretation | null }>(`/api/runs/${id}/interpretation?kind=${kind}&policy=${policy}`),
  interpretationPreview: (id: number, body: { kind: string; policy: string; provider: string; model: string; temperature: number | null }) => j<{ prompt: string | null; scripted: boolean; sent: string }>(`/api/runs/${id}/interpretation/preview`, body),
  interpretationAi: (id: number, body: { kind: string; policy: string; provider: string; model: string; temperature: number | null }, key: string, workspace: string) =>
    j<{ interpretation: Narrative; ai_generated: boolean; provider: string; model_id: string | null; notice: string }>(`/api/runs/${id}/interpretation/ai`, body, { ...(key ? { 'X-Provider-Key': key } : {}), ...(workspace ? { 'X-Provider-Workspace': workspace } : {}) }),
  saveInterpretation: async (id: number, body: { kind: string; policy: string; source: string; narrative: Narrative; notes: string }): Promise<SavedInterpretation> => {
    const r = await fetch(`/api/runs/${id}/interpretation`, { method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-Session': getSid() }, body: JSON.stringify(body) })
    if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail ?? r.statusText)
    return r.json()
  },
  results: (id: number) => j<Results>(`/api/runs/${id}/results`),
}

export type Dashboard = {
  kind: string; metric: string; metric_doc: string; model_policy: string; arms: string[]; reference_solution: string | null
  matrix: { run_id: number; arm: string; rep: number | string; status: string; solution: string | null }[]
  robustness: { path: string; share_by_arm: Record<string, number | null>; across_roles: string }[]
  similarity: { run_id: number; arm: string; score: number }[]
  distinct_solutions: Record<string, number>; valid_runs: Record<string, number>
  path_frequency: { path: string; counts: Record<string, number> }[]
}
export type Rationale = { run_id: number; arm: string; rep: number; variable: string; anchor: string; value: number; rationale: string; source: string; attempt_id: number | null }
export type Attempt = { id: number; run_id: number; kind: string; provider: string; model_id: string | null; prompt_sha256: string; rendered_prompt: string; raw_response: string | null; tokens_in: number | null; tokens_out: number | null; validation_ok: boolean | null; validation_errors: unknown[]; started_at: string }
export const api2 = {
  dashboard: (id: number, kind: string, metric: string, policy: string) => j<Dashboard>(`/api/runs/${id}/dashboard?kind=${kind}&metric=${metric}&policy=${policy}`),
  metrics: () => j<Record<string, string>>('/api/similarity/metrics'),
  rationales: (id: number, arm: string, variable: string) => j<Rationale[]>(`/api/runs/${id}/rationales?${new URLSearchParams({ ...(arm ? { arm } : {}), ...(variable ? { variable } : {}) })}`),
  attempt: (id: number) => j<Attempt>(`/api/attempts/${id}`),
}
