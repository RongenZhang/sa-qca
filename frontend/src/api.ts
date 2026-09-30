export type Stats = { n: number; min: number; q1: number; median: number; q3: number; max: number; mean: number; histogram: { lower: number; upper: number; count: number }[] }
export type Variable = { name: string; role: 'condition' | 'outcome'; direction: string; construct_definition: string; instrument: string; units: string; stats: Stats }
export type Demo = { demo_note?: string; id: string; is_demo: boolean; has_reference: boolean; n_dropped: number; name: string; case_description: string; variables: Variable[]; reference: Record<string, Record<string, number>>; reference_cutoffs: Record<string, number | null>; dir_exp: Record<string, number | null>; warnings: string[]; n_cases: number }
export type UploadInfo = { project_id: string; filename: string; n_rows: number; columns: { name: string; numeric: boolean; n_missing: number; n_unique: number }[]; preview: { header: string[]; rows: (string | null)[][] } }
export type ConfigureBody = { name: string; case_description: string; drop_missing: boolean; reference_cutoffs: Record<string, number | null> | null; variables: { name: string; role: string; direction: string; construct_definition: string; instrument: string; units: string; dir_exp: number | null; anchors: Record<string, number | null> | null }[] }
export type Role = { name: string; description: string; relevance: string; ai?: boolean }
export type RunReq = { project_id: string; role_set_hash: string; arms: { roles: string[]; generic: boolean; mechanical: boolean }; reps: number; provider: string; model: string; temperature: number | null; tolerance: number; spend_cap: number | null; price_in: number | null; price_out: number | null }
export type RunRow = { run_id: number; arm: string; rep: number; status: string; mechanical_id: string | null; attempts: number; anchors: Record<string, Record<string, number>> | null; solutions: Record<'complex' | 'parsimonious' | 'intermediate', string[][]> | null }
export type ArmReport = { n_runs: number; status_counts: Record<string, number>; invalid_rate: number | null; first_attempt_failure_rate: number | null; failure_reasons: Record<string, number> }
export type Status = { provider_errors?: string[]; state: string; total: number; done: number; status_counts: Record<string, number>; report: Record<string, ArmReport> }
export type Results = { config: { id: number; project_id: string; model: string; provider: string; template_version: string; reps: number; arms: string[] }; runs: RunRow[]; report: Record<string, ArmReport>; project: Demo }

async function j<T>(path: string, body?: unknown, headers: Record<string, string> = {}): Promise<T> {
  const r = await fetch(path, body === undefined ? { headers } : { method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) })
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail ?? r.statusText)
  return r.json()
}
export const api = {
  project: (pid: string) => j<Demo>(`/api/projects/${pid}`),
  upload: async (file: File) => {
    const fd = new FormData(); fd.append('file', file)
    const r = await fetch('/api/projects/upload', { method: 'POST', body: fd })
    if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail ?? r.statusText)
    return r.json() as Promise<UploadInfo>
  },
  setup: (pid: string) => j<{ upload: UploadInfo; config: ConfigureBody }>(`/api/projects/${pid}/setup`),
  configure: (pid: string, body: ConfigureBody) => j<Demo>(`/api/projects/${pid}/configure`, body),
  suggest: () => j<{ ai_generated: boolean; roles: Role[] }>('/api/roles/suggest', {}),
  approve: (roles: Role[], approved_by: string) => j<{ roles_hash: string; approved_by: string; approved_at: string }>('/api/roles/approve', { roles, approved_by }),
  preview: (role: Role | null, project_id: string) => j<{ prompt: string; sent_to_provider: string; warnings: string[]; template_version: string }>('/api/prompt/preview', { role, project_id }),
  estimate: (req: RunReq) => j<{ llm_calls_min: number; llm_calls_max: number; mechanical_runs: number; approx_input_tokens_per_call: number; approx_output_tokens_per_call: number; cost_usd_max: number | null }>('/api/runs/estimate', req),
  start: (req: RunReq, key: string, workspace = '') => j<{ run_config_id: number }>('/api/runs', req, { ...(key ? { 'X-Provider-Key': key } : {}), ...(workspace ? { 'X-Provider-Workspace': workspace } : {}) }),
  cancel: (id: number) => j<unknown>(`/api/runs/${id}/cancel`, {}),
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
