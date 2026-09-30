import { useRef, type ReactNode } from 'react'

export function toCsv(rows: Record<string, unknown>[]): string {
  if (!rows.length) return ''
  const cols = Object.keys(rows[0])
  const esc = (v: unknown) => { const t = v === null || v === undefined ? '' : String(v); return /[",\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t }
  return [cols.join(','), ...rows.map((r) => cols.map((c) => esc(r[c])).join(','))].join('\n')
}
function download(name: string, blob: Blob) { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000) }
const slug = (t: string) => t.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

/** Wraps a chart with PNG / SVG / CSV export. `data` is the exact data behind the chart. */
export function ChartFrame({ title, data, children, note }: { title: string; data: Record<string, unknown>[]; children?: ReactNode; note?: string }) {
  const box = useRef<HTMLDivElement>(null)
  const svgText = () => {
    const svg = box.current?.querySelector('svg')
    if (!svg) return null
    const c = svg.cloneNode(true) as SVGSVGElement
    c.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
    return { text: new XMLSerializer().serializeToString(c), w: svg.viewBox.baseVal.width, h: svg.viewBox.baseVal.height }
  }
  const asSvg = () => { const s = svgText(); if (s) download(`${slug(title)}.svg`, new Blob([s.text], { type: 'image/svg+xml' })) }
  const asPng = () => {
    const s = svgText(); if (!s) return
    const img = new Image()
    img.onload = () => { const k = 2, cv = document.createElement('canvas'); cv.width = s.w * k; cv.height = s.h * k; const g = cv.getContext('2d')!; g.scale(k, k); g.drawImage(img, 0, 0, s.w, s.h); cv.toBlob((b) => b && download(`${slug(title)}.png`, b)) }
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(s.text)
  }
  return (
    <figure className="card" style={{ margin: '10px 0' }}>
      <figcaption><h3>{title}</h3>{note && <p className="muted">{note}</p>}</figcaption>
      <div ref={box}>{children}</div>
      <div className="actions" style={{ justifyContent: 'flex-start' }}>
        {children && <><button className="secondary" onClick={asPng}>PNG</button><button className="secondary" onClick={asSvg}>SVG</button></>}
        <button className="secondary" onClick={() => download(`${slug(title)}.csv`, new Blob([toCsv(data)], { type: 'text/csv' }))}>CSV data</button>
      </div>
    </figure>
  )
}
