import type { Stats } from './api'
import { sourceLabel } from './labels'

// Okabe-Ito colour-blind-safe palette. Explicit hex values so exported SVG/PNG render standalone.
export const PALETTE = ['#0072B2', '#E69F00', '#009E73', '#CC79A7', '#56B4E9', '#D55E00', '#F0E442']
export const GENERIC = '#555555', MECH = '#999999'
export const armColors = (arms: string[]) => { let i = 0; const m: Record<string, string> = {}; for (const a of arms) m[a] = a === 'generic' ? GENERIC : a === 'mechanical' ? MECH : PALETTE[i++ % PALETTE.length]; return m }
const INK = '#1d2329', SOFT = '#d9dde1'
const Bg = ({ w, h }: { w: number; h: number }) => <rect width={w} height={h} fill="#ffffff" rx={6} />
const q = (v: number[], p: number) => { const s = [...v].sort((a, b) => a - b), h = (s.length - 1) * p, lo = Math.floor(h), hi = Math.ceil(h); return s[lo] + (h - lo) * (s[hi] - s[lo]) }
const short = (a: string) => { const l = a.startsWith('role:') ? a.slice(5) : sourceLabel(a); return l.length > 16 ? l.slice(0, 15) + '…' : l }

export function SimilarityBox({ data, arms, colors, distinct }: { data: { arm: string; score: number; run_id: number }[]; arms: string[]; colors: Record<string, string>; distinct: Record<string, number> }) {
  const W = 640, H = 340, L = 44, T = 16, B = 70, cw = (W - L - 12) / Math.max(arms.length, 1), y = (v: number) => T + (1 - v) * (H - T - B)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Box plot of similarity to the analyst's solution by anchor source, with every run as a point" fontFamily="system-ui,sans-serif" fontSize={11}>
      <Bg w={W} h={H} />
      {[0, 0.25, 0.5, 0.75, 1].map((t) => <g key={t}><line x1={L} x2={W - 8} y1={y(t)} y2={y(t)} stroke={SOFT} /><text x={L - 6} y={y(t) + 4} textAnchor="end" fill={INK}>{t}</text></g>)}
      {arms.map((a, i) => {
        const pts = data.filter((d) => d.arm === a), cx = L + cw * (i + 0.5), col = colors[a], v = pts.map((p) => p.score)
        return <g key={a}>
          {v.length > 0 && <><line x1={cx} x2={cx} y1={y(Math.max(...v))} y2={y(Math.min(...v))} stroke={col} strokeWidth={2} />
            <rect x={cx - cw * 0.22} width={cw * 0.44} y={y(q(v, 0.75))} height={Math.max(1, y(q(v, 0.25)) - y(q(v, 0.75)))} fill={col} fillOpacity={0.25} stroke={col} strokeWidth={2} />
            <line x1={cx - cw * 0.22} x2={cx + cw * 0.22} y1={y(q(v, 0.5))} y2={y(q(v, 0.5))} stroke={col} strokeWidth={3} /></>}
          {pts.map((p, k) => <circle key={p.run_id} cx={cx + (((k * 37) % 21) - 10) * cw * 0.02} cy={y(p.score)} r={3.2} fill={col} stroke="#fff" strokeWidth={0.8}><title>{`${a} run ${p.run_id}: ${p.score.toFixed(3)}`}</title></circle>)}
          <text x={cx} y={H - B + 16} textAnchor="middle" fill={INK}>{short(a)}</text>
          <text x={cx} y={H - B + 30} textAnchor="middle" fill="#5b6670">n={v.length}</text>
          <text x={cx} y={H - B + 43} textAnchor="middle" fill="#5b6670">{distinct[a] ?? 0} distinct</text></g>
      })}
      <text x={12} y={T + (H - T - B) / 2} transform={`rotate(-90 12 ${T + (H - T - B) / 2})`} textAnchor="middle" fill={INK}>similarity to analyst solution</text>
    </svg>)
}

export function RobustnessHeat({ rows, arms }: { rows: { path: string; share_by_arm: Record<string, number | null> }[]; arms: string[] }) {
  const cw = 92, rh = 30, L = 170, T = 60, W = L + cw * arms.length + 10, H = T + rh * rows.length + 10
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Share of valid runs in which each of the analyst's solution paths survives, by anchor source" fontFamily="system-ui,sans-serif" fontSize={11}>
      <Bg w={W} h={H} />
      {arms.map((a, i) => <text key={a} x={L + cw * (i + 0.5)} y={T - 10} textAnchor="middle" fill={INK}>{short(a)}</text>)}
      {rows.map((r, k) => <g key={r.path}><text x={L - 8} y={T + rh * k + rh / 2 + 4} textAnchor="end" fill={INK}>{r.path}</text>
        {arms.map((a, i) => { const v = r.share_by_arm[a]; return <g key={a}><rect x={L + cw * i + 1} y={T + rh * k + 1} width={cw - 2} height={rh - 2} fill={v === null ? '#f0f0f0' : '#0072B2'} fillOpacity={v === null ? 1 : 0.08 + 0.85 * v} stroke={SOFT} />
          <text x={L + cw * (i + 0.5)} y={T + rh * k + rh / 2 + 4} textAnchor="middle" fill={v !== null && v > 0.55 ? '#fff' : INK}>{v === null ? 'n/a' : `${Math.round(v * 100)}%`}</text></g> })}</g>)}
    </svg>)
}

export function AnchorStrip({ variable, stats, reference, rows, arms, colors }: { variable: string; stats: Stats; reference: Record<string, number>; rows: { arm: string; run_id: number; a: Record<string, number> }[]; arms: string[]; colors: Record<string, string> }) {
  const W = 640, L = 130, H0 = 78, rh = 22, all = ['reference', ...arms], H = H0 + rh * all.length + 22, span = stats.max - stats.min || 1
  const x = (v: number) => L + ((v - stats.min) / span) * (W - L - 12), max = Math.max(...stats.histogram.map((b) => b.count), 1)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={`Anchors proposed for ${variable} by anchor source, over the observed distribution`} fontFamily="system-ui,sans-serif" fontSize={11}>
      <Bg w={W} h={H} />
      {stats.histogram.map((b, i) => <rect key={i} x={x(b.lower) + 1} y={H0 - (b.count / max) * (H0 - 12)} width={Math.max(1, x(b.upper) - x(b.lower) - 2)} height={(b.count / max) * (H0 - 26)} fill="#d9dde1" />)}
      {all.map((a, k) => {
        const yy = H0 + rh * k + rh / 2, col = a === 'reference' ? '#000' : colors[a]
        const rs = a === 'reference' ? [{ run_id: 0, a: reference }] : rows.filter((r) => r.arm === a)
        return <g key={a}><text x={L - 8} y={yy + 4} textAnchor="end" fill={INK}>{a === 'reference' ? "analyst's original" : short(a)}</text>
          {rs.map((r) => <g key={r.run_id}><line x1={x(r.a.full_non_membership)} x2={x(r.a.full_membership)} y1={yy} y2={yy} stroke={col} strokeOpacity={a === 'reference' ? 1 : 0.25} strokeWidth={a === 'reference' ? 2 : 4} strokeDasharray={a === 'reference' ? '5 3' : undefined} />
            <circle cx={x(r.a.crossover)} cy={yy} r={3.2} fill={col} stroke="#fff" strokeWidth={0.8}><title>{`${a} run ${r.run_id}: ${r.a.full_non_membership.toFixed(2)} / ${r.a.crossover.toFixed(2)} / ${r.a.full_membership.toFixed(2)}`}</title></circle></g>)}</g>
      })}
      <text x={L} y={H - 6} fill="#5b6670">{stats.min}</text><text x={W - 12} y={H - 6} textAnchor="end" fill="#5b6670">{stats.max}</text>
      <text x={L} y={12} fill={INK}>{variable}: dot = crossover, bar = full non-membership to full membership</text>
    </svg>)
}
