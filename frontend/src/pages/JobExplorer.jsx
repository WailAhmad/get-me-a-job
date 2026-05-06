import { useState, useEffect, useMemo } from 'react'
import { getJobs, dismissJob, getLiveMode } from '../api/client'
import { useNavigate } from 'react-router-dom'
import { Search, ExternalLink, Briefcase, RefreshCw, Trash2, CheckCircle2, Globe2, Send, Zap, XCircle, AlertTriangle, PlugZap } from 'lucide-react'

/* ───────────────────────── helpers ───────────────────────── */
const scoreColor = (s) => s >= 85 ? '#34d399' : s >= 70 ? '#38bdf8' : '#fbbf24'

/**
 * Bucket a job into one of three categories — we ignore "skipped" entirely,
 * since the user wants to focus only on the valid pipeline.
 *
 *   auto_applied : Easy Apply + already submitted (verified) by the agent
 *   suitable     : Easy Apply + still in the queue (passes score, may have been
 *                  manually clicked but not auto-applied yet)
 *   external     : No Easy Apply — must be opened on the open web
 *   null         : Skipped / dropped — not surfaced anywhere
 */
const SUITABLE_MIN_SCORE = 60   // matches backend scoring threshold

/** Parse a raw error string into a short human-readable reason. */
function parseFailReason(err) {
  if (!err) return 'Unknown error'
  const e = err.toLowerCase()
  if (e.includes('err_internet_disconnected') || e.includes('net::err')) return 'Network disconnected during apply'
  if (e.includes('timeout') || e.includes('timed out'))  return 'Page load timed out'
  if (e.includes('no such element') || e.includes('element not found')) return 'Apply button not found on page'
  if (e.includes('session') && e.includes('deleted'))    return 'Browser session was closed'
  if (e.includes('captcha') || e.includes('challenge'))  return 'CAPTCHA / bot challenge blocked submit'
  if (e.includes('already applied'))                     return 'LinkedIn detected duplicate application'
  if (e.includes('navigation failed'))                   return 'Page navigation failed'
  if (e.includes('stale element'))                       return 'Page changed during form fill'
  if (e.includes('submit') || e.includes('form'))        return 'Form submission failed'
  if (e.includes('login') || e.includes('sign in'))      return 'LinkedIn session expired - re-login needed'
  // Fall back to first line, trimmed to 80 chars
  return err.split('\n')[0].trim().slice(0, 80)
}

function bucketOf(j) {
  if (j.status === 'skipped') return null
  if (j.status === 'failed')  return 'failed'
  if (j.easy_apply && j.submission_verified) return 'auto_applied'
  if (j.easy_apply && (j.score ?? 0) >= SUITABLE_MIN_SCORE) return 'suitable'
  if (!j.easy_apply && j.status !== 'skipped') return 'external'
  return null
}

const BUCKET_META = {
  suitable:     { label: 'Suitable',     color: '#10b981', icon: CheckCircle2 },
  auto_applied: { label: 'Auto-Applied', color: '#34d399', icon: Send         },
  external:     { label: 'External',     color: '#a78bfa', icon: Globe2       },
  failed:       { label: 'Failed',       color: '#ef4444', icon: XCircle      },
}

/** Composite ranker for the External list: recent + relevant. */
const externalRank = (j) => {
  const recency = Math.max(0, 30 - (j.posted_days_ago ?? 30))   // 0…30 (newer = higher)
  const score   = (j.score ?? 0)                                // 0…100
  return recency * 2.5 + score                                  // tunable mix
}

const sortFor = (bucket) => {
  if (bucket === 'auto_applied') return (a,b) => (b.applied_at||0) - (a.applied_at||0)
  if (bucket === 'external')     return (a,b) => externalRank(b) - externalRank(a)
  if (bucket === 'failed')       return (a,b) => (b.score||0) - (a.score||0)  // highest score first so best misses are visible
  // suitable: score first, then recency
  return (a,b) => (b.score||0) - (a.score||0) || (a.posted_days_ago||0) - (b.posted_days_ago||0)
}

/* ───────────────────────── small UI bits ───────────────────────── */
function SummaryCard({ label, value, sub, icon:Icon, color, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className="card"
      style={{
        textAlign:'left',
        padding:16, minHeight:112,
        cursor:'pointer',
        border: active ? `1px solid ${color}66` : '1px solid rgba(255,255,255,0.07)',
        boxShadow: active ? `0 0 0 1px ${color}33, 0 8px 32px ${color}18` : undefined,
        background: active ? `linear-gradient(180deg, ${color}10, rgba(255,255,255,0.02))` : undefined,
        transition:'all .15s',
      }}
    >
      <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:12 }}>
        <div style={{ height:34, width:34, borderRadius:11, background:`${color}18`, border:`1px solid ${color}30`, display:'flex', alignItems:'center', justifyContent:'center' }}>
          <Icon size={16} style={{ color }} />
        </div>
        <div style={{ fontSize:11, color:'#94a3b8', fontWeight:700, textTransform:'uppercase', letterSpacing:'.06em' }}>{label}</div>
      </div>
      <div style={{ fontSize:28, color:'#f8fafc', fontWeight:800, lineHeight:1 }}>{value}</div>
      <div style={{ fontSize:11, color:'#64748b', marginTop:7, lineHeight:1.45 }}>{sub}</div>
    </button>
  )
}

function ApplyBadge({ kind }) {
  const m = BUCKET_META[kind]
  if (!m) return null
  const Icon = m.icon
  return (
    <span style={{
      display:'inline-flex', alignItems:'center', gap:5,
      padding:'3px 9px', borderRadius:99, fontSize:11, fontWeight:600,
      background:`${m.color}14`, color:m.color, border:`1px solid ${m.color}33`,
    }}>
      <Icon size={11} /> {m.label}
    </span>
  )
}

/* ───────────────────────── page ───────────────────────── */
export default function JobExplorer() {
  const navigate = useNavigate()
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(false)
  const [query, setQuery] = useState('')
  const [bucket, setBucket] = useState('suitable')   // default to the queue
  const [visible, setVisible] = useState(60)
  const [liveMode, setLiveMode] = useState(null)

  const load = async () => {
    setLoading(true)
    try {
      const [j, lm] = await Promise.all([getJobs(), getLiveMode().catch(() => null)])
      setJobs(j)
      if (lm) setLiveMode(lm)
    } catch {}
    setLoading(false)
  }
  useEffect(() => { load() }, [])
  useEffect(() => { setVisible(60) }, [bucket, query])

  const remove = async (id) => { await dismissJob(id); setJobs(j => j.filter(x => x.id !== id)) }

  // Pre-bucket once and drop "skipped" entirely.
  const tagged = useMemo(
    () => jobs.map(j => ({ ...j, _bucket: bucketOf(j) })).filter(j => j._bucket),
    [jobs]
  )

  const counts = useMemo(() => {
    const c = { suitable:0, auto_applied:0, external:0, failed:0 }
    tagged.forEach(j => { c[j._bucket] = (c[j._bucket] || 0) + 1 })
    return c
  }, [tagged])

  // Search runs ONLY on the valid (non-skipped) pool, then we filter to the chosen bucket.
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const inQ = (j) => !q
      || j.title?.toLowerCase().includes(q)
      || j.company?.toLowerCase().includes(q)
      || j.location?.toLowerCase().includes(q)
    return tagged.filter(j => j._bucket === bucket && inQ(j)).sort(sortFor(bucket))
  }, [tagged, bucket, query])

  const visibleJobs = filtered.slice(0, visible)

  return (
    <div className="animate-fade-in">
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:8, flexWrap:'wrap', gap:12 }}>
        <div>
          <h1 className="page-title">Job Explorer</h1>
          <p className="page-subtitle">
            Only jobs that pass scoring or come from open-web sources. Skipped jobs are filtered out automatically.
          </p>
        </div>
        <button onClick={load} disabled={loading} className="btn-primary" style={{ gap:6 }}>
          <RefreshCw size={13} style={{ animation:loading?'spin 1s linear infinite':undefined }} /> Refresh
        </button>
      </div>

      {/* ─── search (operates only on the valid pool) ─── */}
      <div style={{ position:'relative', margin:'16px 0' }}>
        <Search size={14} style={{ position:'absolute', left:12, top:'50%', transform:'translateY(-50%)', color:'#64748b' }} />
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search the valid pool — title, company, or location…"
          style={{ paddingLeft:36, width:'100%' }}
        />
      </div>

      {/* ─── Not-connected / no-jobs setup banner ─── */}
      {!loading && jobs.length === 0 && liveMode && !liveMode.linkedin_session && (
        <div style={{ display:'flex', alignItems:'center', gap:14, padding:'14px 18px', borderRadius:14, marginBottom:18,
          background:'rgba(59,130,246,0.06)', border:'1px solid rgba(59,130,246,0.20)' }}>
          <PlugZap size={20} style={{ color:'#60a5fa', flexShrink:0 }} />
          <div style={{ flex:1 }}>
            <div style={{ fontSize:13, fontWeight:700, color:'#93c5fd', marginBottom:2 }}>LinkedIn not connected</div>
            <div style={{ fontSize:12, color:'#64748b', lineHeight:1.5 }}>
              Connect your LinkedIn account to start discovering and applying to jobs. Once connected, run automation from the Dashboard.
            </div>
          </div>
          <button onClick={() => navigate('/settings')} className="btn-primary" style={{ whiteSpace:'nowrap', padding:'8px 14px', fontSize:12 }}>
            Connect →
          </button>
        </div>
      )}

      {/* ─── four category cards (also act as filters) ─── */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))', gap:12, marginBottom:18 }}>
        <SummaryCard
          label="Easy Apply — Suitable"
          value={counts.suitable}
          sub="Score ≥ 60 · queue, including jobs you already clicked"
          icon={CheckCircle2} color="#10b981"
          active={bucket === 'suitable'} onClick={() => setBucket('suitable')}
        />
        <SummaryCard
          label="Auto-Applied"
          value={counts.auto_applied}
          sub="Submitted automatically by the agent (verified)"
          icon={Zap} color="#34d399"
          active={bucket === 'auto_applied'} onClick={() => setBucket('auto_applied')}
        />
        <SummaryCard
          label="External Jobs"
          value={counts.external}
          sub="No Easy Apply · ranked by recency + relevance"
          icon={Globe2} color="#a78bfa"
          active={bucket === 'external'} onClick={() => setBucket('external')}
        />
        <SummaryCard
          label="Failed"
          value={counts.failed}
          sub="Easy Apply attempted but errored — reason shown on each card"
          icon={XCircle} color="#ef4444"
          active={bucket === 'failed'} onClick={() => setBucket('failed')}
        />
      </div>

      {/* ─── list ─── */}
      {loading ? (
        <p style={{ textAlign:'center', color:'#64748b', padding:40 }}>Loading…</p>
      ) : filtered.length === 0 ? (
        <div className="card" style={{ textAlign:'center', padding:40 }}>
          <Briefcase size={32} style={{ color:'#475569', marginBottom:10 }} />
          <p style={{ color:'#64748b' }}>
            {bucket === 'suitable'     && 'No suitable Easy Apply jobs in the queue right now.'}
            {bucket === 'auto_applied' && "The agent has not auto-applied to anything yet."}
            {bucket === 'external'     && 'No external (open-web) jobs discovered yet.'}
            {bucket === 'failed'       && 'No failed apply attempts - great news!'}
          </p>
        </div>
      ) : (
        <>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(380px,1fr))', gap:12 }}>
            {visibleJobs.map(j => {
              const failReason = j._bucket === 'failed' ? parseFailReason(j.error) : null
              return (
              <div key={j.id} className="card" style={{ display:'flex', flexDirection:'column', gap:12, padding:'16px 18px',
                border: j._bucket === 'failed' ? '1px solid rgba(239,68,68,0.22)' : undefined }}>
                <div style={{ display:'flex', alignItems:'flex-start', gap:14, minWidth:0 }}>
                  <div style={{ height:48, width:48, borderRadius:12, background:'rgba(167,139,250,.14)', border:'1px solid rgba(167,139,250,.28)', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0 }}>
                    <span style={{ fontSize:13, fontWeight:700, color:scoreColor(j.score) }}>{j.score ?? '—'}</span>
                  </div>
                  <div style={{ minWidth:0, flex:1 }}>
                    <div style={{ fontSize:16, fontWeight:800, color:'var(--text)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{j.title}</div>
                    <div style={{ fontSize:12, color:'#64748b', marginTop:2 }}>
                      {j.company} · {j.location} · {j.source || 'Source'} · {j.posted_days_ago ?? 0}d ago
                    </div>
                  </div>
                  <ApplyBadge kind={j._bucket} />
                </div>

                {/* ── Failure reason banner ── */}
                {failReason && (
                  <div style={{ display:'flex', alignItems:'flex-start', gap:8, padding:'10px 12px', borderRadius:12,
                    background:'rgba(239,68,68,0.07)', border:'1px solid rgba(239,68,68,0.20)' }}>
                    <AlertTriangle size={13} style={{ color:'#f87171', flexShrink:0, marginTop:1 }} />
                    <div>
                      <div style={{ fontSize:11, fontWeight:700, color:'#f87171', marginBottom:2 }}>Why it failed</div>
                      <div style={{ fontSize:12, color:'#fca5a5', lineHeight:1.45 }}>{failReason}</div>
                    </div>
                  </div>
                )}

                <div style={{ display:'grid', gridTemplateColumns:'repeat(3,minmax(0,1fr))', gap:8 }}>
                  <div style={{ background:'rgba(255,255,255,.035)', border:'1px solid rgba(255,255,255,.06)', borderRadius:12, padding:10 }}>
                    <div style={{ fontSize:10, color:'#64748b', textTransform:'uppercase', letterSpacing:'.05em', fontWeight:700 }}>Apply type</div>
                    <div style={{ fontSize:13, color:'var(--text-secondary)', marginTop:4 }}>
                      {j.easy_apply ? 'Easy Apply' : 'External'}
                    </div>
                  </div>
                  <div style={{ background:'rgba(255,255,255,.035)', border:'1px solid rgba(255,255,255,.06)', borderRadius:12, padding:10 }}>
                    <div style={{ fontSize:10, color:'#64748b', textTransform:'uppercase', letterSpacing:'.05em', fontWeight:700 }}>
                      {j._bucket === 'auto_applied' ? 'Submitted' : j._bucket === 'failed' ? 'Attempted' : 'Found'}
                    </div>
                    <div style={{ fontSize:13, color:'var(--text-secondary)', marginTop:4 }}>
                      {(j._bucket === 'auto_applied' ? j.applied_at : j.discovered_at)
                        ? new Date(((j._bucket === 'auto_applied' ? j.applied_at : j.discovered_at)) * 1000)
                            .toLocaleString([], { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' })
                        : '—'}
                    </div>
                  </div>
                  <div style={{ background:'rgba(255,255,255,.035)', border:'1px solid rgba(255,255,255,.06)', borderRadius:12, padding:10 }}>
                    <div style={{ fontSize:10, color:'#64748b', textTransform:'uppercase', letterSpacing:'.05em', fontWeight:700 }}>Match</div>
                    <div style={{ fontSize:12, color:scoreColor(j.score), marginTop:4 }}>
                      {j.score >= 85 ? 'Strong' : j.score >= 70 ? 'Good' : j.score ? 'Borderline' : '—'}
                    </div>
                  </div>
                </div>

                <div style={{ display:'flex', gap:8, alignItems:'center', justifyContent:'space-between' }}>
                  {j.url ? (
                    <a href={j.url} target="_blank" rel="noreferrer" className="btn-primary" style={{ gap:6, padding:'8px 14px', fontSize:12 }}>
                      Open <ExternalLink size={12}/>
                    </a>
                  ) : (
                    <span style={{ color:'#475569', fontSize:11 }}>No live URL</span>
                  )}
                  <button onClick={()=>remove(j.id)} title="Dismiss" style={{ background:'none', border:'1px solid rgba(255,255,255,0.06)', borderRadius:10, padding:8, color:'#475569', cursor:'pointer' }}>
                    <Trash2 size={13}/>
                  </button>
                </div>
              </div>
            )})}
          </div>
          {visible < filtered.length && (
            <div style={{ display:'flex', justifyContent:'center', marginTop:18 }}>
              <button className="btn-secondary" onClick={() => setVisible(v => v + 60)}>
                Show more <span style={{ opacity:.7 }}>({Math.min(60, filtered.length - visible)} more)</span>
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
