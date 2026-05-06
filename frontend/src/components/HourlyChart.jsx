/**
 * Hourly activity chart — shared between Dashboard and Job Explorer.
 *
 * Buckets jobs by the hour of `discovered_at` and `applied_at`, then renders
 * three line series: jobs found, verified applied, external jobs.
 */

const hourKey = (ts) => {
  if (!ts) return null
  const d = new Date(ts * 1000)
  d.setMinutes(0, 0, 0)
  return d.toISOString()
}

export function buildHourlySeries(jobs) {
  const map = new Map()
  jobs.forEach(job => {
    const discoveredKey = hourKey(job.discovered_at)
    if (discoveredKey) {
      const row = map.get(discoveredKey) || { key: discoveredKey, label: new Date(discoveredKey).toLocaleTimeString([], { hour:'2-digit', minute:'2-digit' }), found:0, applied:0, external:0 }
      row.found += 1
      if (job.status === 'external') row.external += 1
      map.set(discoveredKey, row)
    }
    const appliedKey = hourKey(job.applied_at)
    if (appliedKey && job.submission_verified) {
      const row = map.get(appliedKey) || { key: appliedKey, label: new Date(appliedKey).toLocaleTimeString([], { hour:'2-digit', minute:'2-digit' }), found:0, applied:0, external:0 }
      row.applied += 1
      map.set(appliedKey, row)
    }
  })
  return Array.from(map.values()).sort((a,b) => new Date(a.key) - new Date(b.key)).slice(-24)
}

export default function HourlyChart({ jobs, title = 'Hourly Activity', subtitle = 'New jobs found, verified applied, and external jobs by hour' }) {
  const data = buildHourlySeries(jobs || [])
  const width = 760
  const height = 210
  const pad = 30
  const max = Math.max(1, ...data.flatMap(d => [d.found, d.applied, d.external]))
  const x = (i) => data.length <= 1 ? pad : pad + (i * (width - pad * 2)) / (data.length - 1)
  const y = (v) => height - pad - (v * (height - pad * 2)) / max
  const path = (key) => data.map((d,i) => `${i === 0 ? 'M' : 'L'} ${x(i)} ${y(d[key])}`).join(' ')
  const series = [
    ['found',    '#38bdf8', 'Found'],
    ['external', '#a78bfa', 'External'],
    ['applied',  '#34d399', 'Applied'],
  ]

  return (
    <div className="card" style={{ padding:18, overflow:'hidden' }}>
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:12, marginBottom:10, flexWrap:'wrap' }}>
        <div>
          <div style={{ fontSize:14, fontWeight:800, color:'var(--text)' }}>{title}</div>
          <div style={{ fontSize:12, color:'var(--text-muted)', marginTop:2 }}>{subtitle}</div>
        </div>
        <div style={{ display:'flex', gap:10, flexWrap:'wrap' }}>
          {series.map(([key, color, label]) => (
            <span key={key} style={{ display:'flex', alignItems:'center', gap:6, color:'var(--text-muted)', fontSize:11 }}>
              <span style={{ height:7, width:7, borderRadius:'50%', background:color }} /> {label}
            </span>
          ))}
        </div>
      </div>
      {!data.length ? (
        <div style={{ textAlign:'center', padding:'30px 0', color:'var(--text-muted)', fontSize:12 }}>
          No hourly activity yet — run the automation to populate this chart.
        </div>
      ) : (
        <svg viewBox={`0 0 ${width} ${height}`} style={{ width:'100%', height:220, display:'block' }}>
          {[0, .25, .5, .75, 1].map((t, i) => {
            const yy = pad + t * (height - pad * 2)
            return <line key={i} x1={pad} x2={width-pad} y1={yy} y2={yy} stroke="rgba(148,163,184,.12)" strokeDasharray="4 5" />
          })}
          {series.map(([key, color]) => (
            <path key={key} d={path(key)} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
          ))}
          {series.map(([key, color]) => (
            data.map((d, i) => (
              <circle key={`${key}-${i}`} cx={x(i)} cy={y(d[key])} r="3" fill={color} />
            ))
          ))}
          {data.map((d,i) => (
            <g key={d.key}>
              <text x={x(i)} y={height - 6} fill="var(--text-muted)" fontSize="10" textAnchor="middle">{d.label}</text>
            </g>
          ))}
          <text x={8} y={pad + 4} fill="var(--text-muted)" fontSize="10">{max}</text>
          <text x={14} y={height - pad + 4} fill="var(--text-muted)" fontSize="10">0</text>
        </svg>
      )}
    </div>
  )
}
