import { useState, useEffect } from 'react'
import { getPendingJobs, answerPendingJob, dismissJob } from '../api/client'
import { Clock, Send, BookmarkPlus, ShieldAlert, Trash2, Sparkles, HelpCircle } from 'lucide-react'

function suggestedAnswer(job) {
  const q = (job.pending_question || '').toLowerCase()
  if (q.includes('notice')) return '30 days'
  if (q.includes('salary')) return ''
  if (q.includes('sponsor') || q.includes('visa')) return 'No'
  if (q.includes('relocat')) return 'Yes'
  if (q.includes('english') || q.includes('proficiency')) return 'Native / Bilingual'
  if (q.includes('authorized') || q.includes('work authorization')) return 'Yes'
  if (q.includes('experience') && /\byear/.test(q)) return String(Math.max(0, Number(job.years || 15)))
  return ''
}

function pendingExplanation(job) {
  const q = (job.pending_question || '').toLowerCase()
  if (job.pending_kind === 'verify_source') return 'The app found a candidate but does not trust the live source URL enough to submit automatically.'
  if (q.includes('please make a selection')) return 'LinkedIn rejected a required dropdown/radio choice. The retry needs the exact option to select.'
  if (q.includes('valid answer')) return 'LinkedIn validation rejected the typed value. Use the exact format requested by the form.'
  if (q.includes('salary')) return 'This is a sensitive answer. JobsLand should use your saved preference or ask you before submitting.'
  return 'The agent paused instead of guessing because the answer affects a real application.'
}

export default function PendingReview({ onAnswered }) {
  const [jobs, setJobs] = useState([])
  const [drafts, setDrafts] = useState({})    // jobId -> answer
  const [savePref, setSavePref] = useState({}) // jobId -> save_to_bank
  const [busy, setBusy] = useState({})
  const [messages, setMessages] = useState({})

  const load = async () => { try { setJobs(await getPendingJobs()) } catch {} }
  useEffect(() => { load() }, [])

  const submit = async (job) => {
    const ans = drafts[job.id]
    if (!ans?.trim()) return
    setBusy(b => ({ ...b, [job.id]: true }))
    setMessages(m => ({ ...m, [job.id]: '' }))
    try {
      const result = await answerPendingJob(job.id, ans.trim(), savePref[job.id] !== false)
      if (result?.success) {
        setJobs(j => j.filter(x => x.id !== job.id))
        onAnswered && onAnswered()
      } else {
        setMessages(m => ({ ...m, [job.id]: result?.message || 'LinkedIn still needs review.' }))
        await load()
      }
    } catch (e) {
      setMessages(m => ({ ...m, [job.id]: e?.response?.data?.detail || e.message || 'Retry failed.' }))
    } finally { setBusy(b => ({ ...b, [job.id]: false })) }
  }

  const useSuggestion = (job) => {
    const suggestion = suggestedAnswer(job)
    if (!suggestion) return
    setDrafts(d => ({ ...d, [job.id]: suggestion }))
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
        JobsLand pauses here only when an Easy Apply form needs a real answer, validation failed, or a safe automatic answer is not available.
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
                    <div style={{ fontSize:15, fontWeight:700, color:'var(--text)' }}>{j.title}</div>
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
                  <div style={{ fontSize:14, color:'var(--text)' }}>{j.pending_question}</div>
                </div>

                <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(220px,1fr))', gap:10, marginBottom:10 }}>
                  <div style={{ padding:12, borderRadius:12, border:'1px solid var(--border)', background:'var(--bg-subtle)' }}>
                    <div style={{ display:'flex', alignItems:'center', gap:6, fontSize:12, fontWeight:800, color:'var(--text)', marginBottom:6 }}>
                      <HelpCircle size={13} /> Why it paused
                    </div>
                    <div style={{ fontSize:12, lineHeight:1.55, color:'var(--text-muted)' }}>{pendingExplanation(j)}</div>
                  </div>
                  <div style={{ padding:12, borderRadius:12, border:'1px solid var(--border)', background:'var(--bg-subtle)' }}>
                    <div style={{ display:'flex', alignItems:'center', gap:6, fontSize:12, fontWeight:800, color:'var(--text)', marginBottom:6 }}>
                      <Sparkles size={13} /> Suggested next action
                    </div>
                    {suggestedAnswer(j) ? (
                      <div style={{ display:'flex', alignItems:'center', gap:8, flexWrap:'wrap' }}>
                        <span className="badge badge-blue">{suggestedAnswer(j)}</span>
                        <button onClick={() => useSuggestion(j)} className="btn-secondary" style={{ padding:'6px 10px', fontSize:12 }}>
                          Use suggestion
                        </button>
                      </div>
                    ) : (
                      <div style={{ fontSize:12, lineHeight:1.55, color:'var(--text-muted)' }}>
                        Type the exact answer or add it in Settings as a reusable application preference.
                      </div>
                    )}
                  </div>
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
                  {messages[j.id] && (
                    <div style={{ width:'100%', fontSize:12, color:'#fbbf24', marginBottom:4 }}>{messages[j.id]}</div>
                  )}
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
