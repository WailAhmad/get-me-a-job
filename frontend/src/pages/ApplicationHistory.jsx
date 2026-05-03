import { useState, useEffect } from 'react'
import { getAppliedJobs } from '../api/client'
import { History, ExternalLink, ShieldAlert, CheckCircle2 } from 'lucide-react'

export default function ApplicationHistory() {
  const [apps, setApps] = useState([])
  const [loading, setLoading] = useState(true)
  useEffect(() => { getAppliedJobs().then(setApps).catch(()=>{}).finally(()=>setLoading(false)) }, [])

  const badgeStyle = (status, verified) => {
    if (status === 'already_applied') return { bg: 'rgba(14,165,233,.12)', border: 'rgba(14,165,233,.28)', color: '#38bdf8', label: 'Already Applied' }
    if (verified) return { bg: 'rgba(16,185,129,.12)', border: 'rgba(16,185,129,.28)', color: '#34d399', label: 'Submitted' }
    return { bg: 'rgba(251,191,36,.12)', border: 'rgba(251,191,36,.28)', color: '#fbbf24', label: 'Needs verification' }
  }

  return (
    <div className="animate-fade-in">
      <h1 className="page-title">Application History</h1>
      <p className="page-subtitle" style={{ marginBottom:20 }}>All submitted and previously applied jobs on LinkedIn.</p>

      {loading ? <p style={{ textAlign:'center', color:'#64748b', padding:40 }}>Loading…</p> :
       apps.length === 0
        ? <div className="card" style={{ textAlign:'center', padding:40 }}><History size={32} style={{ color:'#475569', marginBottom:10 }} /><p style={{ color:'#64748b' }}>No applications yet — start automation from the Dashboard.</p></div>
        : <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
            {apps.map(a => {
              const badge = badgeStyle(a.status, a.submission_verified)
              return (
              <div key={a.id} className="card" style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:12 }}>
                <div style={{ display:'flex', alignItems:'center', gap:14, minWidth:0 }}>
                  <div style={{ height:38, width:38, borderRadius:10, background:`${badge.bg}`, border:`1px solid ${badge.border}`, display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0 }}>
                    <span style={{ fontSize:11, fontWeight:700, color:badge.color }}>{a.score}</span>
                  </div>
                  <div style={{ minWidth:0 }}>
                    <div style={{ fontSize:14, fontWeight:600, color:'#f1f5f9', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{a.title}</div>
                    <div style={{ fontSize:12, color:'#64748b', marginTop:2 }}>
                      {a.company} · {a.location}{a.applied_at ? ` · ${new Date(a.applied_at*1000).toLocaleDateString()}` : ''}
                    </div>
                  </div>
                </div>
                <div style={{ display:'flex', alignItems:'center', gap:8, flexShrink:0 }}>
                  <span style={{ fontSize:11, fontWeight:600, padding:'4px 10px', borderRadius:8, background:badge.bg, border:`1px solid ${badge.border}`, color:badge.color }}>{badge.label}</span>
                  {a.url && a.url_verified && <a href={a.url} target="_blank" rel="noreferrer" style={{ color:'#64748b', display:'flex' }}><ExternalLink size={14} /></a>}
                </div>
              </div>
            )})}
          </div>}
    </div>
  )
}
