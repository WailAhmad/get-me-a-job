import { useState, useEffect } from 'react'
import { getPendingJobs, answerPendingJob, dismissJob } from '../api/client'
import { Clock, Send, BookmarkPlus, ShieldAlert, Trash2 } from 'lucide-react'

export default function PendingReview({ onAnswered }) {
  const [jobs, setJobs] = useState([])
  const [drafts, setDrafts] = useState({})    // jobId -> answer
  const [savePref, setSavePref] = useState({}) // jobId -> save_to_bank
  const [busy, setBusy] = useState({})

  const load = async () => { try { setJobs(await getPendingJobs()) } catch {} }
  useEffect(() => { load() }, [])

  const submit = async (job) => {
    const ans = drafts[job.id]
    if (!ans?.trim()) return
    setBusy(b => ({ ...b, [job.id]: true }))
    try {
      await answerPendingJob(job.id, ans.trim(), savePref[job.id] !== false)
      setJobs(j => j.filter(x => x.id !== job.id))
      onAnswered && onAnswered()
    } finally { setBusy(b => ({ ...b, [job.id]: false })) }
  }

  const dismiss = async (jobId) => {
    try {
      await dismissJob(jobId)
      setJobs(j => j.filter(x => x.id !== jobId))
    } catch {}
  }

  return (
    <div className="animate-fade-in">
      <h1 className="page-title">Pending Review</h1>
      <p className="page-subtitle" style={{ marginBottom:20 }}>
        Jobs the bot tried to apply to but couldn't answer one of the questions. Answer once and we'll remember it for next time.
      </p>

      {jobs.length === 0
        ? <div className="card" style={{ textAlign:'center', padding:40 }}>
            <Clock size={32} style={{ color:'#475569', marginBottom:10 }} />
            <p style={{ color:'#64748b' }}>Nothing pending — keep automation running and any unknown questions will appear here.</p>
          </div>
        : <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            {jobs.map(j => (
              <div key={j.id} className="card">
                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:14, gap:10 }}>
                  <div style={{ minWidth:0, flex:1 }}>
                    <div style={{ fontSize:14, fontWeight:600, color:'#f1f5f9' }}>{j.title}</div>
                    <div style={{ fontSize:12, color:'#64748b', marginTop:2 }}>{j.company} · {j.location} · {j.score}% match</div>
                  </div>
                  <div style={{ display:'flex', alignItems:'center', gap:8, flexShrink:0 }}>
                    <span className="badge" style={{ background:'rgba(245,158,11,.1)', color:'#fbbf24', border:'1px solid rgba(245,158,11,.25)' }}>Needs your answer</span>
                    <button
                      onClick={() => dismiss(j.id)}
                      title="Dismiss this job"
                      style={{ background:'none', border:'1px solid rgba(255,255,255,0.07)', borderRadius:8, padding:'5px 7px', color:'#475569', cursor:'pointer', display:'flex', alignItems:'center' }}
                    >
                      <Trash2 size={13}/>
                    </button>
                  </div>
                </div>

                <div style={{ padding:12, borderRadius:12, background:'rgba(245,158,11,0.05)', border:'1px solid rgba(245,158,11,0.18)', marginBottom:10 }}>
                  <div style={{ fontSize:11, fontWeight:600, color:'#fbbf24', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:6 }}>
                    {j.pending_kind === 'verify_source' ? 'Verification required' : 'Question'}
                  </div>
                  <div style={{ fontSize:13, color:'#f1f5f9' }}>{j.pending_question}</div>
                </div>

                {j.pending_kind === 'verify_source' ? (
                  <div style={{ display:'flex', alignItems:'center', gap:8, color:'#fbbf24', fontSize:12, marginBottom:10 }}>
                    <ShieldAlert size={14} /> This item was prepared by the local matching engine. It needs a verified live job URL before submission.
                  </div>
                ) : (
                  <textarea
                    value={drafts[j.id] || ''}
                    onChange={e => setDrafts({ ...drafts, [j.id]: e.target.value })}
                    placeholder="Type your answer…"
                    rows={2}
                    style={{ width:'100%', resize:'vertical', marginBottom:10 }}
                  />
                )}

                <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:10, flexWrap:'wrap' }}>
                  {j.pending_kind !== 'verify_source' && (
                    <>
                      <label style={{ display:'flex', alignItems:'center', gap:6, fontSize:12, color:'#94a3b8', cursor:'pointer' }}>
                        <input type="checkbox" checked={savePref[j.id] !== false} onChange={e => setSavePref({ ...savePref, [j.id]: e.target.checked })} />
                        <BookmarkPlus size={13} /> Save answer to memory (auto-fill next time)
                      </label>
                      <button onClick={() => submit(j)} disabled={busy[j.id] || !drafts[j.id]?.trim()} className="btn-primary" style={{ gap:6 }}>
                        <Send size={12} /> {busy[j.id] ? 'Submitting…' : 'Answer & Apply'}
                      </button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>}
    </div>
  )
}
