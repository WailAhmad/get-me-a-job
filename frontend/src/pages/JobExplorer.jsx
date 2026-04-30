import { useState, useEffect } from 'react'
import { getJobs, dismissJob } from '../api/client'
import { Search, ExternalLink, Briefcase, RefreshCw, Trash2, ShieldAlert, CheckCircle2, Clock, Globe2, Layers3 } from 'lucide-react'

const scoreColor = (s) => s >= 85 ? '#34d399' : s >= 70 ? '#38bdf8' : '#fbbf24'
const statusLabel = {
  discovered: 'Discovered',
  external: 'External',
  pending: 'Pending',
  applied: 'Applied',
  skipped: 'Skipped',
}
const statusClass = {
  discovered: 'badge-blue',
  external: 'badge-blue',
  pending: 'badge-amber',
  applied: 'badge-green',
  skipped: 'badge-gray',
}
const PAGE_SIZE = 60

const hourKey = (ts) => {
  if (!ts) return null
  const d = new Date(ts * 1000)
  d.setMinutes(0, 0, 0)
  return d.toISOString()
}

function buildHourlySeries(jobs) {
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

function MiniLineChart({ data }) {
  const width = 760
  const height = 210
  const pad = 30
  const max = Math.max(1, ...data.flatMap(d => [d.found, d.applied, d.external]))
  const x = (i) => data.length <= 1 ? pad : pad + (i * (width - pad * 2)) / (data.length - 1)
  const y = (v) => height - pad - (v * (height - pad * 2)) / max
  const path = (key) => data.map((d,i) => `${i === 0 ? 'M' : 'L'} ${x(i)} ${y(d[key])}`).join(' ')
  const series = [
    ['found', '#38bdf8', 'Found'],
    ['external', '#a78bfa', 'External'],
    ['applied', '#34d399', 'Verified applied'],
  ]
  if (!data.length) {
    return <div className="card" style={{ padding:24, color:'#64748b', fontSize:13 }}>No hourly activity yet.</div>
  }
  return (
    <div className="card" style={{ padding:18, overflow:'hidden' }}>
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:12, marginBottom:10, flexWrap:'wrap' }}>
        <div>
          <div style={{ fontSize:14, fontWeight:700, color:'#f1f5f9' }}>Hourly Activity</div>
          <div style={{ fontSize:12, color:'#64748b', marginTop:2 }}>New jobs found, verified applied, and external jobs by hour</div>
        </div>
        <div style={{ display:'flex', gap:10, flexWrap:'wrap' }}>
          {series.map(([key, color, label]) => (
            <span key={key} style={{ display:'flex', alignItems:'center', gap:6, color:'#94a3b8', fontSize:11 }}>
              <span style={{ height:7, width:7, borderRadius:'50%', background:color }} /> {label}
            </span>
          ))}
        </div>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width:'100%', height:220, display:'block' }}>
        {[0, .25, .5, .75, 1].map((t, i) => {
          const yy = pad + t * (height - pad * 2)
          return <line key={i} x1={pad} x2={width-pad} y1={yy} y2={yy} stroke="rgba(148,163,184,.12)" strokeDasharray="4 5" />
        })}
        {series.map(([key, color]) => (
          <path key={key} d={path(key)} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        ))}
        {data.map((d,i) => (
          <g key={d.key}>
            <text x={x(i)} y={height - 6} fill="#475569" fontSize="10" textAnchor="middle">{d.label}</text>
          </g>
        ))}
        <text x={8} y={pad + 4} fill="#64748b" fontSize="10">{max}</text>
        <text x={14} y={height - pad + 4} fill="#64748b" fontSize="10">0</text>
      </svg>
    </div>
  )
}

function SummaryCard({ label, value, sub, icon:Icon, color }) {
  return (
    <div className="card" style={{ padding:16, minHeight:112 }}>
      <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:12 }}>
        <div style={{ height:34, width:34, borderRadius:11, background:`${color}18`, border:`1px solid ${color}30`, display:'flex', alignItems:'center', justifyContent:'center' }}>
          <Icon size={16} style={{ color }} />
        </div>
        <div style={{ fontSize:11, color:'#94a3b8', fontWeight:700, textTransform:'uppercase', letterSpacing:'.06em' }}>{label}</div>
      </div>
      <div style={{ fontSize:28, color:'#f8fafc', fontWeight:800, lineHeight:1 }}>{value}</div>
      <div style={{ fontSize:11, color:'#64748b', marginTop:7, lineHeight:1.45 }}>{sub}</div>
    </div>
  )
}

export default function JobExplorer() {
  const [jobs, setJobs]     = useState([])
  const [loading, setLoading] = useState(false)
  const [query, setQuery]   = useState('')
  const [filter, setFilter] = useState('all')
  const [visible, setVisible] = useState(PAGE_SIZE)

  const load = async () => { setLoading(true); try { setJobs(await getJobs()) } catch {} finally { setLoading(false) } }
  useEffect(() => { load() }, [])

  const remove = async (id) => { await dismissJob(id); setJobs(j => j.filter(x => x.id !== id)) }

  const counts = jobs.reduce((acc, job) => {
    acc.all += 1
    acc[job.status] = (acc[job.status] || 0) + 1
    return acc
  }, { all:0 })
  const filtered = jobs.filter(j => {
    const matchesFilter = filter === 'all' || j.status === filter
    const q = query.toLowerCase()
    const matchesQuery = !q || j.title?.toLowerCase().includes(q) || j.company?.toLowerCase().includes(q) || j.location?.toLowerCase().includes(q)
    return matchesFilter && matchesQuery
  })
  const visibleJobs = filtered.slice(0, visible)
  const easyCandidates = jobs.filter(j => j.easy_apply).length
  const verifiedUrls = jobs.filter(j => j.url_verified).length
  const verifiedApplied = jobs.filter(j => j.submission_verified).length
  const hourly = buildHourlySeries(jobs)

  useEffect(() => { setVisible(PAGE_SIZE) }, [filter, query])

  return (
    <div className="animate-fade-in">
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:8, flexWrap:'wrap', gap:12 }}>
        <div>
          <h1 className="page-title">Job Explorer</h1>
          <p className="page-subtitle">All discovered jobs from the latest runs, including discovered, external, pending, skipped, and applied records</p>
        </div>
        <button onClick={load} disabled={loading} className="btn-primary" style={{ gap:6 }}>
          <RefreshCw size={13} style={{ animation:loading?'spin 1s linear infinite':undefined }} /> Refresh
        </button>
      </div>

      <div style={{ position:'relative', margin:'16px 0' }}>
        <Search size={14} style={{ position:'absolute', left:12, top:'50%', transform:'translateY(-50%)', color:'#64748b' }} />
        <input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search by title or company…" style={{ paddingLeft:36, width:'100%' }} />
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(190px,1fr))', gap:12, marginBottom:14 }}>
        <SummaryCard label="Total Found" value={jobs.length} sub="Complete inventory in this page" icon={Layers3} color="#38bdf8" />
        <SummaryCard label="Easy Apply Candidates" value={easyCandidates} sub="Blocked until live URLs are verified" icon={CheckCircle2} color="#10b981" />
        <SummaryCard label="Verified URLs" value={verifiedUrls} sub="Required before real submission" icon={ShieldAlert} color="#fbbf24" />
        <SummaryCard label="External Jobs" value={counts.external || 0} sub="Need manual/open-web apply" icon={Globe2} color="#a78bfa" />
      </div>

      <div style={{ marginBottom:16 }}>
        <MiniLineChart data={hourly} />
      </div>

      <div style={{ display:'flex', gap:8, flexWrap:'wrap', marginBottom:16 }}>
        {['all','discovered','external','pending','applied','skipped'].map(key => (
          <button key={key} onClick={() => setFilter(key)} className={filter === key ? 'btn-primary' : 'btn-secondary'} style={{ padding:'7px 11px', fontSize:12 }}>
            {key === 'all' ? 'All' : statusLabel[key]} <span style={{ opacity:.75 }}>{counts[key] || 0}</span>
          </button>
        ))}
      </div>

      {loading ? <p style={{ textAlign:'center', color:'#64748b', padding:40 }}>Loading…</p> :
       filtered.length === 0 ? (
         <div className="card" style={{ textAlign:'center', padding:40 }}>
           <Briefcase size={32} style={{ color:'#475569', marginBottom:10 }} />
           <p style={{ color:'#64748b' }}>No jobs match this view yet.</p>
         </div>
       ) :
       <>
       <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(360px,1fr))', gap:12 }}>
         {visibleJobs.map(j => (
           <div key={j.id} className="card" style={{ display:'flex', flexDirection:'column', gap:12, padding:'16px 18px' }}>
             <div style={{ display:'flex', alignItems:'flex-start', gap:14, minWidth:0 }}>
               <div style={{ height:48, width:48, borderRadius:12, background:'rgba(167,139,250,.14)', border:'1px solid rgba(167,139,250,.28)', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0 }}>
                 <span style={{ fontSize:13, fontWeight:700, color:scoreColor(j.score) }}>{j.score}</span>
               </div>
               <div style={{ minWidth:0, flex:1 }}>
                 <div style={{ fontSize:15, fontWeight:700, color:'#f1f5f9', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{j.title}</div>
                 <div style={{ fontSize:12, color:'#64748b', marginTop:2 }}>
                   {j.company} · {j.location} · {j.source || 'Source'} · posted {j.posted_days_ago||0}d ago
                 </div>
               </div>
               <span className={`badge ${statusClass[j.status] || 'badge-gray'}`}>{statusLabel[j.status] || j.status}</span>
             </div>

             <div style={{ display:'grid', gridTemplateColumns:'repeat(3,minmax(0,1fr))', gap:8 }}>
               <div style={{ background:'rgba(255,255,255,.035)', border:'1px solid rgba(255,255,255,.06)', borderRadius:12, padding:10 }}>
                 <div style={{ fontSize:10, color:'#64748b', textTransform:'uppercase', letterSpacing:'.05em', fontWeight:700 }}>Apply type</div>
                 <div style={{ fontSize:12, color:'#cbd5e1', marginTop:4 }}>{j.apply_type || (j.easy_apply ? 'Easy Apply' : 'External')}</div>
               </div>
               <div style={{ background:'rgba(255,255,255,.035)', border:'1px solid rgba(255,255,255,.06)', borderRadius:12, padding:10 }}>
                 <div style={{ fontSize:10, color:'#64748b', textTransform:'uppercase', letterSpacing:'.05em', fontWeight:700 }}>Verified URL</div>
                 <div style={{ fontSize:12, color:j.url_verified ? '#34d399' : '#fbbf24', marginTop:4 }}>{j.url_verified ? 'Yes' : 'No'}</div>
               </div>
               <div style={{ background:'rgba(255,255,255,.035)', border:'1px solid rgba(255,255,255,.06)', borderRadius:12, padding:10 }}>
                 <div style={{ fontSize:10, color:'#64748b', textTransform:'uppercase', letterSpacing:'.05em', fontWeight:700 }}>Found</div>
                 <div style={{ fontSize:12, color:'#cbd5e1', marginTop:4 }}>{j.discovered_at ? new Date(j.discovered_at*1000).toLocaleTimeString([], { hour:'2-digit', minute:'2-digit' }) : '—'}</div>
               </div>
             </div>

             {!j.url_verified && (
               <div style={{ display:'flex', alignItems:'flex-start', gap:7, color:'#fbbf24', fontSize:11, lineHeight:1.45, background:'rgba(245,158,11,.07)', border:'1px solid rgba(245,158,11,.16)', borderRadius:12, padding:'9px 10px' }}>
                 <ShieldAlert size={13} style={{ flexShrink:0, marginTop:1 }} /> Easy Apply is blocked until the automation captures the real live job posting URL.
               </div>
             )}

             <div style={{ display:'flex', gap:8, alignItems:'center', justifyContent:'space-between' }}>
               {j.url_verified ? (
                 <a href={j.url} target="_blank" rel="noreferrer" className="btn-primary" style={{ gap:6, padding:'8px 14px', fontSize:12 }}>
                   Open <ExternalLink size={12}/>
                 </a>
               ) : (
                 <button disabled className="btn-secondary" title={j.url_warning || 'No verified live job URL captured'} style={{ gap:6, padding:'8px 14px', fontSize:12, opacity:.55, cursor:'not-allowed' }}>
                   Unverified
                 </button>
               )}
               <button onClick={()=>remove(j.id)} title="Dismiss" style={{ background:'none', border:'1px solid rgba(255,255,255,0.06)', borderRadius:10, padding:8, color:'#475569', cursor:'pointer' }}>
                 <Trash2 size={13}/>
               </button>
             </div>
           </div>
         ))}
       </div>
       {visible < filtered.length && (
         <div style={{ display:'flex', justifyContent:'center', marginTop:18 }}>
           <button className="btn-secondary" onClick={() => setVisible(v => v + PAGE_SIZE)}>
             Show more jobs <span style={{ opacity:.7 }}>({Math.min(PAGE_SIZE, filtered.length - visible)} more)</span>
           </button>
         </div>
       )}
       </>}
    </div>
  )
}
