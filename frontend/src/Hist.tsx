import type { Stats } from './api'

export function Hist({ stats, marks = [], label }: { stats: Stats; marks?: number[]; label: string }) {
  const W = 320, H = 70, max = Math.max(...stats.histogram.map((b) => b.count), 1)
  const span = stats.max - stats.min || 1
  return (
    <svg className="hist" viewBox={`0 0 ${W} ${H + 14}`} role="img" aria-label={label} width="100%">
      {stats.histogram.map((b, i) => {
        const w = W / stats.histogram.length, h = (b.count / max) * H
        return <rect key={i} x={i * w + 1} y={H - h} width={w - 2} height={h}><title>{`${b.lower.toFixed(2)}–${b.upper.toFixed(2)}: ${b.count}`}</title></rect>
      })}
      {marks.map((m, i) => <line key={i} x1={((m - stats.min) / span) * W} x2={((m - stats.min) / span) * W} y1={0} y2={H} stroke="var(--warn)" strokeWidth={2} strokeDasharray="4 3" />)}
      <text x={0} y={H + 12} fontSize={10} fill="currentColor">{stats.min}</text>
      <text x={W} y={H + 12} fontSize={10} fill="currentColor" textAnchor="end">{stats.max}</text>
    </svg>
  )
}
