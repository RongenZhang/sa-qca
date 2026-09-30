export type Stats = { n: number; min: number; q1: number; median: number; q3: number; max: number; mean: number; histogram: { lower: number; upper: number; count: number }[] }
export type Variable = { name: string; role: 'condition' | 'outcome'; direction: string; construct_definition: string; instrument: string; units: string; stats: Stats }
export type Demo = { name: string; case_description: string; variables: Variable[]; reference: Record<string, Record<string, number>>; reference_cutoffs: Record<string, number | null>; dir_exp: Record<string, number | null>; warnings: string[]; n_cases: number }
export type Role = { name: string; description: string; relevance: string; ai?: boolean }
export type RunReq = { role_set_hash: string; arms: { roles: string[]; generic: boolean; mechanical: boolean }; reps: number; provider: string; model: string; temperature: number | null; tolerance: number; spend_cap: number | null; price_in: number | null; price_out: number | null }
export type RunRow = { run_id: number; arm: string; rep: number; status: string; mechanical_id: string | null; attempts: number; anchors: Record<string, Record<string, number>> | null; solutions: Record<'complex' | 'parsimonious' | 'intermediate', string[][]> | null }
export type ArmReport = { n_runs: number; status_counts: Record<string, number>; invalid_rate: number | null; first_attempt_failure_rate: number | null; failure_reasons: Record<string, number> }
export type Status = { state: string; total: number; done: number; status_counts: Record<string, number>; report: Record<string, ArmReport> }
export type Results = { config: { id: number; model: string; provider: string; template_version: string; reps: number; arms: string[] }; runs: RunRow[]; report: Record<string, ArmReport> }

async function j<T>(path: string, body?: unknown, headers: Record<string, string> = {}): Promise<T> {
  const r = await fetch(path, body === undefined ? { headers } : { method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) })
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail ?? r.statusText)
  return r.json()
}
export const api = {
  demo: () => j<Demo>('/api/demo'),
  suggest: () => j<{ ai_generated: boolean; roles: Role[] }>('/api/roles/suggest', {}),
  approve: (roles: Role[], approved_by: string) => j<{ roles_hash: string; approved_by: string; approved_at: string }>('/api/roles/approve', { roles, approved_by }),
  preview: (role: Role | null) => j<{ prompt: string; sent_to_provider: string; warnings: string[]; template_version: string }>('/api/prompt/preview', { role }),
  estimate: (req: RunReq) => j<{ llm_calls_min: number; llm_calls_max: number; mechanical_runs: number; approx_input_tokens_per_call: number; approx_output_tokens_per_call: number; cost_usd_max: number | null }>('/api/runs/estimate', req),
  start: (req: RunReq, key: string) => j<{ run_config_id: number }>('/api/runs', req, key ? { 'X-Provider-Key': key } : {}),
  cancel: (id: number) => j<unknown>(`/api/runs/${id}/cancel`, {}),
  results: (id: number) => j<Results>(`/api/runs/${id}/results`),
}
