import { useState, useEffect } from 'react'
import { getAppliedJobs } from '../api/client'
import { History, ExternalLink, ShieldAlert } from 'lucide-react'

export default function ApplicationHistory() {
  const [apps, setApps] = useState([])
  const [loading, setLoading] = useState(true)
  useEffect(() => { getAppliedJobs().then(setApps).catch(()=>{}).finally(()=>setLoading(false)) }, [])

  return (
    <div className="animate-fade-in">
      <h1 className="page-title">Application History</h1>
      <p className="page-subtitle" style={{ marginBottom:20 }}>Submitted applications and any older recorded actions that still need verification.</p>

      {loading ? <p style={{ textAlign:'center', color:'#64748b', padding:40 }}>Loading…</p> :
       apps.length === 0
        ? <div className="card" style={{ textAlign:'center', padding:40 }}><History size={32} style={{ color:'#475569', marginBottom:10 }} /><p style={{ color:'#64748b' }}>No applications yet — start automation from the Dashboard.</p></div>
        : <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
            {apps.map(a => (
              <div key={a.id} className="card" style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:12 }}>
                <div style={{ display:'flex', alignItems:'center', gap:14, minWidth:0 }}>
                  <div style={{ height:38, width:38, borderRadius:10, background:'rgba(16,185,129,.14)', border:'1px solid rgba(16,185,129,.28)', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0 }}>
                    <span style={{ fontSize:11, fontWeight:700, color:'#34d399' }}>{a.score}</span>
                  </div>
                  <div style={{ minWidth:0 }}>
                    <div style={{ fontSize:14, fontWeight:600, color:'#f1f5f9', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{a.title}</div>
                    <div style={{ fontSize:12, color:'#64748b', marginTop:2 }}>
                      {a.company} · {a.location} · {a.submission_verified ? 'submitted' : 'recorded'} {a.applied_at ? new Date(a.applied_at*1000).toLocaleString() : '—'}
                    </div>
                    {!a.submission_verified && (
                      <div style={{ display:'flex', alignItems:'center', gap:5, color:'#fbbf24', fontSize:11, marginTop:6 }}>
                        <ShieldAlert size={12} /> Not verified as a real submitted application.
                      </div>
                    )}
                  </div>
                </div>
                <div style={{ display:'flex', alignItems:'center', gap:8, flexShrink:0 }}>
                  <span className={`badge ${a.submission_verified ? 'badge-green' : 'badge-amber'}`}>{a.submission_verified ? 'Submitted' : 'Needs verification'}</span>
                  {a.url && a.url_verified && <a href={a.url} target="_blank" rel="noreferrer" style={{ color:'#64748b', display:'flex' }}><ExternalLink size={14} /></a>}
                </div>
              </div>
            ))}
          </div>}
    </div>
  )
}
