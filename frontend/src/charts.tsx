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
  const W = 640, H = 360, L = 52, T = 16, B = 84, cw = (W - L - 12) / Math.max(arms.length, 1), y = (v: number) => T + (1 - v) * (H - T - B)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Similarity of each run's solution to the analyst's solution, by anchor source. Each circle is one or more runs with the same score; the number inside is how many." fontFamily="system-ui,sans-serif" fontSize={11}>
      <Bg w={W} h={H} />
      {[[0, 'nothing in common'], [0.5, ''], [1, 'same solution']].map(([t, lab]) => <g key={String(t)}><line x1={L} x2={W - 8} y1={y(+t)} y2={y(+t)} stroke={SOFT} /><text x={L - 6} y={y(+t) + 4} textAnchor="end" fill={INK}>{t}</text>{lab && <text x={W - 10} y={y(+t) - 4} textAnchor="end" fill="#5b6670" fontSize={10}>{lab}</text>}</g>)}
      {arms.map((a, i) => {
        const pts = data.filter((d) => d.arm === a), cx = L + cw * (i + 0.5), col = colors[a], v = pts.map((p) => p.score)
        const groups = new Map<number, number[]>()
        pts.forEach((p) => groups.set(p.score, [...(groups.get(p.score) ?? []), p.run_id]))
        const many = groups.size >= 3  // a box only makes sense when the scores actually vary
        return <g key={a}>
          {many && <><line x1={cx} x2={cx} y1={y(Math.max(...v))} y2={y(Math.min(...v))} stroke={col} strokeWidth={2} />
            <rect x={cx - cw * 0.3} width={cw * 0.6} y={y(q(v, 0.75))} height={Math.max(1, y(q(v, 0.25)) - y(q(v, 0.75)))} fill={col} fillOpacity={0.2} stroke={col} strokeWidth={2} />
            <line x1={cx - cw * 0.3} x2={cx + cw * 0.3} y1={y(q(v, 0.5))} y2={y(q(v, 0.5))} stroke={col} strokeWidth={3} /></>}
          {[...groups.entries()].map(([score, ids]) => { const r = 7 + Math.min(10, Math.sqrt(ids.length) * 2.5)
            return <g key={score}><circle cx={cx} cy={y(score)} r={r} fill={col} fillOpacity={0.85} stroke="#fff" strokeWidth={1.5}><title>{`${a}: score ${score.toFixed(2)}, ${ids.length} run(s): #${ids.join(', #')}`}</title></circle>
              <text x={cx} y={y(score) + 4} textAnchor="middle" fill="#fff" fontWeight={700} fontSize={11}>{ids.length}</text></g> })}
          <text x={cx} y={H - B + 16} textAnchor="middle" fill={INK}>{short(a)}</text>
          <text x={cx} y={H - B + 30} textAnchor="middle" fill="#5b6670">{v.length} runs</text>
          <text x={cx} y={H - B + 43} textAnchor="middle" fill="#5b6670">{distinct[a] ?? 0} distinct solution{(distinct[a] ?? 0) === 1 ? '' : 's'}</text></g>
      })}
      <text x={12} y={T + (H - T - B) / 2} transform={`rotate(-90 12 ${T + (H - T - B) / 2})`} textAnchor="middle" fill={INK}>similarity to the analyst's solution</text>
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

const TRI_KEYS = [['full_non_membership', 'crossover', 'full_membership'], ['break_0', 'break_33', 'break_67']]
const tri = (a: Record<string, number>): number[] => (TRI_KEYS.find((ks) => ks.every((k) => k in a)) ?? TRI_KEYS[0]).map((k) => a[k])

export function AnchorStrip({ variable, stats, reference, rows, arms, colors, kind = 'direct' }: { variable: string; stats: Stats; reference?: Record<string, number>; rows: { arm: string; run_id: number; a: Record<string, number> }[]; arms: string[]; colors: Record<string, string>; kind?: string }) {
  const bp = kind === 'breakpoints'
  const logScale = bp && stats.max > 10 * Math.max(stats.q3, 1)  // skewed counts: a linear axis would squash every boundary at the left edge
  const T = (v: number) => (logScale ? Math.log10(1 + Math.max(v, 0)) : v), lo = T(stats.min), hi = T(stats.max), span = hi - lo || 1
  const W = 640, L = 130, H0 = 78, rh = 22, all = [...(reference ? ['reference'] : []), ...arms], H = H0 + rh * all.length + 22
  const x = (v: number) => Math.max(L, Math.min(W - 12, L + ((T(v) - lo) / span) * (W - L - 12))), max = Math.max(...stats.histogram.map((b) => b.count), 1)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={`${bp ? 'Breakpoints' : 'Anchors'} proposed for ${variable} by anchor source, over the observed distribution`} fontFamily="system-ui,sans-serif" fontSize={11}>
      <Bg w={W} h={H} />
      {stats.histogram.map((b, i) => <rect key={i} x={x(b.lower) + 1} y={H0 - (b.count / max) * (H0 - 26)} width={Math.max(1, x(b.upper) - x(b.lower) - 2)} height={(b.count / max) * (H0 - 26)} fill="#d9dde1" />)}
      {all.map((a, k) => {
        const yy = H0 + rh * k + rh / 2, col = a === 'reference' ? '#000' : colors[a]
        const rs = a === 'reference' && reference ? [{ run_id: 0, a: reference }] : rows.filter((r) => r.arm === a)
        return <g key={a}><text x={L - 8} y={yy + 4} textAnchor="end" fill={INK}>{a === 'reference' ? "analyst's original" : short(a)}</text>
          {rs.map((r) => { const [p0, p1, p2] = tri(r.a)
            return <g key={r.run_id}><line x1={x(p0)} x2={x(p2)} y1={yy} y2={yy} stroke={col} strokeOpacity={a === 'reference' ? 1 : 0.25} strokeWidth={a === 'reference' ? 2 : 4} strokeDasharray={a === 'reference' ? '5 3' : undefined} />
              {bp ? [p0, p1, p2].map((p, i) => <line key={i} x1={x(p)} x2={x(p)} y1={yy - 6} y2={yy + 6} stroke={col} strokeWidth={2}><title>{`${a} run ${r.run_id}: boundary ${['0|0.33', '0.33|0.67', '0.67|1'][i]} at ${p.toFixed(2)}`}</title></line>)
                : <circle cx={x(p1)} cy={yy} r={3.2} fill={col} stroke="#fff" strokeWidth={0.8}><title>{`${a} run ${r.run_id}: ${p0.toFixed(2)} / ${p1.toFixed(2)} / ${p2.toFixed(2)}`}</title></circle>}</g> })}</g>
      })}
      <text x={L} y={H - 6} fill="#5b6670">{stats.min}</text><text x={W - 12} y={H - 6} textAnchor="end" fill="#5b6670">{stats.max}{logScale ? ' (log scale)' : ''}</text>
      <text x={L} y={12} fill={INK}>{variable}: {bp ? 'ticks = the three breakpoints between scores 0 | 0.33 | 0.67 | 1' : 'dot = crossover, bar = full non-membership to full membership'}</text>
    </svg>)
}
