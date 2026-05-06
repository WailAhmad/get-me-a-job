import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getDashboardStats, getAutomationStatus, stopAutomation, startAutomation, clearJobs, getJobs, getLiveMode } from '../api/client'
import { CheckCircle, Clock, Globe2, Play, Square, Radio, FileText, MessageSquare, AlertTriangle, Layers3, Trash2, XCircle, Zap, Brain } from 'lucide-react'
import AutomationPanel from '../components/AutomationPanel'
import HourlyChart from '../components/HourlyChart'

/* ── section header ──────────────────────────────────────────────── */
function SectionLabel({ tag, tagColor, label, sub }) {
  return (
    <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:12 }}>
      <span style={{
        fontSize:10, fontWeight:700, letterSpacing:'.1em', textTransform:'uppercase',
        padding:'3px 10px', borderRadius:99,
        background: `${tagColor}18`, color: tagColor,
        border: `1px solid ${tagColor}35`,
      }}>{tag}</span>
      <span style={{ fontSize:13, fontWeight:600, color:'var(--text-secondary)' }}>{label}</span>
      {sub && <span style={{ fontSize:11, color:'var(--text-muted)' }}>· {sub}</span>}
    </div>
  )
}

/* ── applied card (two sub-tags) ────────────────────────────────── */
function AppliedCard({ byApp, already, onClick }) {
  const total = (byApp ?? 0) + (already ?? 0)
  return (
    <button onClick={onClick}
      style={{
        textAlign:'left', cursor:'pointer', gridColumn:'span 1',
        background:'linear-gradient(180deg, rgba(16,185,129,0.09), var(--bg-card))',
        border:'1px solid rgba(16,185,129,0.35)',
        borderRadius:18, padding:18, position:'relative', overflow:'hidden',
        transition:'all .2s', width:'100%',
      }}
      onMouseEnter={e => { e.currentTarget.style.borderColor='rgba(16,185,129,0.6)'; e.currentTarget.style.transform='translateY(-1px)' }}
      onMouseLeave={e => { e.currentTarget.style.borderColor='rgba(16,185,129,0.35)'; e.currentTarget.style.transform='translateY(0)' }}
    >
      <div style={{ position:'absolute', right:-14, top:-14, height:60, width:60, borderRadius:'50%', background:'#10b98114', filter:'blur(2px)' }} />
      <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:10 }}>
        <div style={{ height:32, width:32, borderRadius:10, background:'#10b98118', display:'flex', alignItems:'center', justifyContent:'center' }}>
          <CheckCircle size={15} style={{ color:'#10b981' }} />
        </div>
        <div style={{ fontSize:11, fontWeight:700, color:'var(--text-muted)', textTransform:'uppercase', letterSpacing:'.06em' }}>Applied</div>
      </div>
      <div style={{ fontSize:30, fontWeight:800, color:'var(--text)', lineHeight:1, marginBottom:10 }}>{total}</div>
      <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
        <span style={{ fontSize:11, fontWeight:600, padding:'3px 9px', borderRadius:99, background:'rgba(16,185,129,0.14)', color:'#34d399', border:'1px solid rgba(16,185,129,0.28)' }}>
          {byApp ?? 0} by app
        </span>
        <span style={{ fontSize:11, fontWeight:600, padding:'3px 9px', borderRadius:99, background:'rgba(14,165,233,0.14)', color:'#38bdf8', border:'1px solid rgba(14,165,233,0.28)' }}>
          {already ?? 0} already applied
        </span>
      </div>
    </button>
  )
}

/* ── Easy Apply card (merged with Already Applied) ───────────── */
function EasyApplyCard({ easyApplyTotal, newApps, already, pending, queued, filtered, scanning, onClick }) {
  const total = (easyApplyTotal ?? 0) + (already ?? 0)
  return (
    <button onClick={onClick}
      style={{
        textAlign:'left', cursor:'pointer', gridColumn:'span 1',
        background:'linear-gradient(180deg, rgba(20,184,166,0.10), var(--bg-card))',
        border:'1px solid rgba(20,184,166,0.35)',
        borderRadius:18, padding:18, position:'relative', overflow:'hidden',
        transition:'all .2s', width:'100%',
      }}
      onMouseEnter={e => { e.currentTarget.style.borderColor='rgba(20,184,166,0.6)'; e.currentTarget.style.transform='translateY(-1px)' }}
      onMouseLeave={e => { e.currentTarget.style.borderColor='rgba(20,184,166,0.35)'; e.currentTarget.style.transform='translateY(0)' }}
    >
      <div style={{ position:'absolute', right:-14, top:-14, height:60, width:60, borderRadius:'50%', background:'#14b8a614', filter:'blur(2px)' }} />
      <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:10 }}>
        <div style={{ height:32, width:32, borderRadius:10, background:'#14b8a618', display:'flex', alignItems:'center', justifyContent:'center' }}>
          <Zap size={15} style={{ color:'#14b8a6' }} />
        </div>
        <div style={{ fontSize:11, fontWeight:700, color:'var(--text-muted)', textTransform:'uppercase', letterSpacing:'.06em' }}>Easy Apply</div>
      </div>
      <div style={{ fontSize:30, fontWeight:800, color:'var(--text)', lineHeight:1, marginBottom:10 }}>{scanning ? '…' : total}</div>
      {scanning ? (
        <div style={{ fontSize:12, color:'var(--text-muted)' }}>scanning…</div>
      ) : (
        <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
          <span style={{ fontSize:11, fontWeight:600, padding:'3px 9px', borderRadius:99, background:'rgba(20,184,166,0.14)', color:'#2dd4bf', border:'1px solid rgba(20,184,166,0.28)' }}>
            {newApps ?? 0} applied this run
          </span>
          {(pending ?? 0) > 0 && (
            <span style={{ fontSize:11, fontWeight:600, padding:'3px 9px', borderRadius:99, background:'rgba(245,158,11,0.14)', color:'#fbbf24', border:'1px solid rgba(245,158,11,0.28)' }}>
              {pending} pending
            </span>
          )}
          {(queued ?? 0) > 0 && (
            <span style={{ fontSize:11, fontWeight:600, padding:'3px 9px', borderRadius:99, background:'rgba(99,102,241,0.14)', color:'#a5b4fc', border:'1px solid rgba(99,102,241,0.28)' }}>
              {queued} queued
            </span>
          )}
          <span style={{ fontSize:11, fontWeight:600, padding:'3px 9px', borderRadius:99, background:'rgba(14,165,233,0.14)', color:'#38bdf8', border:'1px solid rgba(14,165,233,0.28)' }}>
            {already ?? 0} already applied
          </span>
          {(filtered ?? 0) > 0 && (
            <span style={{ fontSize:11, fontWeight:600, padding:'3px 9px', borderRadius:99, background:'rgba(100,116,139,0.10)', color:'var(--text-muted)', border:'1px solid var(--border)' }}>
              {filtered} below match
            </span>
          )}
        </div>
      )}
    </button>
  )
}

/* ── stat card ───────────────────────────────────────────────────── */
const Card = ({ title, value, sub, icon:Icon, color, onClick, accent }) => (
  <button onClick={onClick}
    style={{
      textAlign:'left', cursor: onClick?'pointer':'default',
      background:'var(--bg-card)',
      border:`1px solid ${accent ? color+'40' : 'var(--border)'}`,
      borderRadius:18, padding:18, position:'relative', overflow:'hidden',
      transition:'all .2s', width:'100%',
    }}
    onMouseEnter={e => { if(onClick){ e.currentTarget.style.borderColor = color+'66'; e.currentTarget.style.transform='translateY(-1px)' } }}
    onMouseLeave={e => { e.currentTarget.style.borderColor = accent ? color+'40' : 'var(--border)'; e.currentTarget.style.transform='translateY(0)' }}
  >
    <div style={{ position:'absolute', right:-14, top:-14, height:60, width:60, borderRadius:'50%', background:color+'14', filter:'blur(2px)' }} />
    <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:10 }}>
      <div style={{ height:32, width:32, borderRadius:10, background:color+'18', display:'flex', alignItems:'center', justifyContent:'center' }}>
        <Icon size={15} style={{ color }} />
      </div>
      <div style={{ fontSize:11, fontWeight:700, color:'var(--text-muted)', textTransform:'uppercase', letterSpacing:'.06em' }}>{title}</div>
    </div>
    <div style={{ fontSize:30, fontWeight:800, color:'var(--text)', lineHeight:1 }}>{value ?? '—'}</div>
    {sub && <div style={{ fontSize:11, color:'var(--text-muted)', marginTop:6 }}>{sub}</div>}
  </button>
)

const Countdown = ({ targetTime, running }) => {
  const [remaining, setRemaining] = useState('')
  useEffect(() => {
    if (running || !targetTime) return
    const id = setInterval(() => {
      const diff = Math.max(0, targetTime - Date.now() / 1000)
      if (diff === 0) {
        setRemaining('Starting soon…')
      } else {
        const m = Math.floor(diff / 60)
        const s = Math.floor(diff % 60)
        setRemaining(`Next run in ${m}m ${s}s`)
      }
    }, 1000)
    return () => clearInterval(id)
  }, [targetTime, running])
  
  if (running) return null
  if (!targetTime) return null
  return (
    <div style={{ display:'flex', alignItems:'center', gap:6, padding:'6px 12px', background:'var(--bg-card)', borderRadius:8, border:'1px solid var(--border)' }}>
      <Clock size={14} color="#94a3b8" />
      <span style={{ fontSize:13, color:'var(--text-muted)', fontWeight:600, fontFamily:'monospace' }}>{remaining}</span>
    </div>
  )
}

export default function Dashboard({ cv, prefs, onRefresh }) {
  const navigate = useNavigate()
  const [stats,    setStats]    = useState(null)
  const [jobs,     setJobs]     = useState([])
  const [running,  setRunning]  = useState(false)
  const [nextRunAt, setNextRunAt] = useState(null)
  const [busy,     setBusy]     = useState(false)
  const [clearing, setClearing] = useState(false)
  const [error,    setError]    = useState('')
  const [liveMode, setLiveModeState] = useState({ live_mode:false, linkedin_session:false, effective:false })

  const refresh = async () => {
    try { setStats(await getDashboardStats()) } catch {}
    try { 
      const s = await getAutomationStatus()
      setRunning(s?.running ?? false)
      setNextRunAt(s?.next_run_at)
    } catch {}
    try { setJobs(await getJobs()) } catch {}
    try { setLiveModeState(await getLiveMode()) } catch {}
  }

  useEffect(() => {
    refresh()
    const interval = running ? 2000 : 5000
    const id = setInterval(refresh, interval)
    return () => clearInterval(id)
  }, [running])

  const handleClear = async () => {
    if (!confirm('Clear all discovered jobs and reset counters? Older runs (with stuck pending items) will be wiped so the next run starts clean.')) return
    setClearing(true)
    try { await clearJobs(); await refresh(); onRefresh && onRefresh() } finally { setClearing(false) }
  }

  const handleStart = async () => {
    setBusy(true); setError('')
    try {
      const r = await startAutomation()
      if (r.success === false) setError(r.message || 'Could not start')
      else setRunning(true)
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Could not start automation')
    } finally { setBusy(false) }
  }

  const handleStop = async () => {
    setBusy(true)
    try { await stopAutomation(); setRunning(false) } finally { setBusy(false) }
  }

  const cvOK    = !!cv?.uploaded
  const prefsOK = !!prefs?.ready
  const linkedinOK = !!liveMode.linkedin_session
  const canRun  = cvOK && prefsOK && linkedinOK
  const setupTarget = !cvOK ? '/cv' : !prefsOK ? '/chat' : '/settings'
  const setupLabel = !cvOK ? 'Upload CV →' : !prefsOK ? 'Talk to Jobby →' : 'Connect LinkedIn →'
  const setupTitle = !cvOK
    ? 'Upload your CV first'
    : !prefsOK
      ? 'Talk to Jobby first to set your search preferences'
      : 'Connect your LinkedIn account in Settings'

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:24, flexWrap:'wrap', gap:12 }}>
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-subtitle">Your 24/7 LinkedIn application autopilot</p>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:14 }}>
          <Countdown targetTime={nextRunAt} running={running} />
          {running ? (
            <button onClick={handleStop} disabled={busy} style={{ display:'flex', alignItems:'center', gap:7, padding:'9px 16px', borderRadius:12, border:'1px solid rgba(239,68,68,0.25)', background:'rgba(239,68,68,0.07)', color:'#f87171', fontSize:13, fontWeight:600, cursor:'pointer' }}>
              <Square size={13} /> {busy ? 'Stopping…' : 'Stop Automation'}
            </button>
          ) : (
            <button
              onClick={canRun ? handleStart : () => navigate(setupTarget)}
              disabled={busy}
              className="btn-primary"
              style={{ gap:8, opacity: canRun ? 1 : 0.6 }}
              title={canRun ? '' : setupTitle}
            >
              <Play size={13} /> {canRun ? 'Run Automation' : setupLabel}
            </button>
          )}
        </div>
      </div>

      {/* Real automation readiness banner */}
      <div onClick={() => navigate('/settings')}
        style={{
          display:'flex', alignItems:'center', gap:10, padding:'10px 14px', borderRadius:14,
          marginBottom:14, cursor:'pointer',
          background: liveMode.effective ? 'rgba(16,185,129,0.06)' : 'rgba(245,158,11,0.05)',
          border: `1px solid ${liveMode.effective ? 'rgba(16,185,129,0.20)' : 'rgba(245,158,11,0.20)'}`,
        }}>
        <span style={{ height:8, width:8, borderRadius:'50%', background: liveMode.effective ? '#34d399' : '#fbbf24', flexShrink:0,
          boxShadow: liveMode.effective ? '0 0 6px #34d399' : 'none', animation: liveMode.effective ? 'pulse 1.6s ease-in-out infinite' : 'none' }} />
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{ fontSize:13, fontWeight:700, color: liveMode.effective ? '#34d399' : '#fbbf24' }}>
            {liveMode.effective ? 'LIVE MODE — real LinkedIn submissions' : 'REAL MODE NOT READY'}
          </div>
          <div style={{ fontSize:11, color:'var(--text-muted)', marginTop:1 }}>
            {liveMode.effective
              ? 'Automation drives a real Selenium browser using your saved LinkedIn session. No limits — applies to all matched jobs.'
              : (liveMode.linkedin_session
                  ? 'Live mode is OFF. Click here to enable real submissions in Settings.'
                  : 'Connect your LinkedIn session in Settings to unlock live mode.')}
          </div>
        </div>
        <span style={{ fontSize:12, color:'#0ea5e9', fontWeight:600 }}>Settings →</span>
      </div>

      {/* How it works */}
      <div className="card" style={{ marginBottom:20 }}>
        <div style={{ fontSize:13, fontWeight:600, color:'#64748b', marginBottom:16, textTransform:'uppercase', letterSpacing:'.06em' }}>How It Works</div>
        <div style={{ display:'flex', alignItems:'flex-start', gap:0, flexWrap:'wrap' }}>
          {[
            { n:'1', title:'Upload Your CV',           desc:'Drop your CV — we extract skills and years to match jobs semantically.', color:'#3b82f6' },
            { n:'2', title:'Chat with Jobby',         desc:'Set country, recency, and target roles in natural language.',           color:'#14b8a6' },
            { n:'3', title:'Run Automation',           desc:'We auto-apply to Easy Apply matches and route the rest to External / Pending.',  color:'#a78bfa' },
          ].map((s, i) => (
            <div key={i} style={{ flex:'1 1 220px', display:'flex', alignItems:'flex-start', gap:12, padding:'0 16px', borderRight: i<2 ? '1px solid var(--border)' : 'none' }}>
              <div style={{ width:28, height:28, borderRadius:8, background:`${s.color}18`, border:`1px solid ${s.color}30`, display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0, fontSize:12, fontWeight:700, color:s.color }}>{s.n}</div>
              <div>
                <div style={{ fontSize:13, fontWeight:700, color:'var(--text)', marginBottom:4 }}>{s.title}</div>
                <div style={{ fontSize:12, color:'var(--text-muted)', lineHeight:1.6 }}>{s.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Setup gate banner */}
      {!canRun && (
        <div className="card" style={{ background:'linear-gradient(135deg, rgba(245,158,11,0.08), rgba(56,189,248,0.04))', border:'1px solid rgba(245,158,11,0.18)', marginBottom:20 }}>
          <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom:14 }}>
            <AlertTriangle size={18} style={{ color:'#f59e0b', flexShrink:0 }} />
            <div>
              <div style={{ fontSize:14, fontWeight:700, color:'#b45309' }}>Finish setting up before automation can run</div>
              <div style={{ fontSize:12, color:'var(--text-muted)', marginTop:2 }}>Upload your CV, talk to Jobby, then connect LinkedIn before any automation starts.</div>
            </div>
          </div>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(220px,1fr))', gap:10 }}>
            <button onClick={() => navigate('/cv')} style={{ textAlign:'left', display:'flex', gap:12, alignItems:'center', padding:14, borderRadius:14, border:`1px solid ${cvOK?'rgba(16,185,129,0.25)':'rgba(59,130,246,0.25)'}`, background:cvOK?'rgba(16,185,129,0.06)':'rgba(59,130,246,0.06)', cursor:'pointer' }}>
              <div style={{ height:36, width:36, borderRadius:10, background: cvOK?'rgba(16,185,129,0.16)':'rgba(59,130,246,0.16)', display:'flex', alignItems:'center', justifyContent:'center' }}>
                {cvOK ? <CheckCircle size={16} style={{ color:'#34d399' }} /> : <FileText size={16} style={{ color:'#60a5fa' }} />}
              </div>
              <div>
                <div style={{ fontSize:13, fontWeight:700, color:'var(--text)' }}>1. {cvOK ? 'CV uploaded' : 'Upload your CV'}</div>
                <div style={{ fontSize:11, color:'var(--text-muted)', marginTop:2 }}>{cvOK ? `${cv.skills?.length||0} skills · ${cv.years||0} years` : 'PDF or DOCX — used to match jobs'}</div>
              </div>
            </button>
            <button onClick={() => navigate('/chat')} disabled={!cvOK} style={{ textAlign:'left', display:'flex', gap:12, alignItems:'center', padding:14, borderRadius:14, border:`1px solid ${prefsOK?'rgba(16,185,129,0.25)':'rgba(20,184,166,0.25)'}`, background:prefsOK?'rgba(16,185,129,0.06)':'rgba(20,184,166,0.06)', cursor:cvOK?'pointer':'not-allowed', opacity:cvOK?1:0.5 }}>
              <div style={{ height:36, width:36, borderRadius:10, background: prefsOK?'rgba(16,185,129,0.16)':'rgba(20,184,166,0.16)', display:'flex', alignItems:'center', justifyContent:'center' }}>
                {prefsOK ? <CheckCircle size={16} style={{ color:'#34d399' }} /> : <MessageSquare size={16} style={{ color:'#2dd4bf' }} />}
              </div>
              <div>
                <div style={{ fontSize:13, fontWeight:700, color:'var(--text)' }}>2. {prefsOK ? 'Preferences set' : 'Chat with Jobby'}</div>
                <div style={{ fontSize:11, color:'var(--text-muted)', marginTop:2 }}>{prefsOK ? `${prefs.country} · last ${prefs.recency_days} days` : 'Country, recency, target roles'}</div>
              </div>
            </button>
            <button onClick={() => navigate('/settings')} disabled={!cvOK || !prefsOK} style={{ textAlign:'left', display:'flex', gap:12, alignItems:'center', padding:14, borderRadius:14, border:`1px solid ${linkedinOK?'rgba(16,185,129,0.25)':'rgba(14,165,233,0.25)'}`, background:linkedinOK?'rgba(16,185,129,0.06)':'rgba(14,165,233,0.06)', cursor:(cvOK&&prefsOK)?'pointer':'not-allowed', opacity:(cvOK&&prefsOK)?1:0.5 }}>
              <div style={{ height:36, width:36, borderRadius:10, background: linkedinOK?'rgba(16,185,129,0.16)':'rgba(14,165,233,0.16)', display:'flex', alignItems:'center', justifyContent:'center' }}>
                {linkedinOK ? <CheckCircle size={16} style={{ color:'#34d399' }} /> : <Radio size={16} style={{ color:'#38bdf8' }} />}
              </div>
              <div>
                <div style={{ fontSize:13, fontWeight:700, color:'var(--text)' }}>3. {linkedinOK ? 'LinkedIn connected' : 'Connect LinkedIn'}</div>
                <div style={{ fontSize:11, color:'var(--text-muted)', marginTop:2 }}>{linkedinOK ? 'Browser session ready' : 'Required for live job discovery and apply'}</div>
              </div>
            </button>
          </div>
        </div>
      )}

      {error && (
        <div style={{ background:'rgba(239,68,68,.08)', border:'1px solid rgba(239,68,68,.2)', borderRadius:12, padding:'10px 14px', fontSize:12, color:'#fca5a5', marginBottom:14 }}>{error}</div>
      )}

      {/* ── LAST RUN section ───────────────────────────────────── */}
      <SectionLabel tag="Last Run" tagColor="#38bdf8" label="Results from the most recent automation run" />
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(190px,1fr))', gap:12, marginBottom:22 }}>
        <Card title="Matched Jobs"   value={running && stats?.live_found > 0 ? stats?.live_matched : stats?.last_run_matched} sub={running && stats?.live_found > 0 ? `scanning… ${stats?.live_found ?? 0} found so far` : `${(stats?.last_run_easy_apply ?? 0) + (stats?.last_run_easy_already ?? 0)} easy apply · ${stats?.last_run_external ?? 0} external`} icon={Layers3} color="#3b82f6" onClick={() => navigate('/jobs')} />
        <EasyApplyCard newApps={stats?.last_run_applied ?? 0} easyApplyTotal={running && stats?.live_found > 0 ? stats?.live_easy_apply : (stats?.last_run_easy_apply ?? 0)} already={stats?.last_run_easy_already ?? 0} pending={stats?.last_run_easy_pending ?? 0} queued={stats?.last_run_easy_queue ?? 0} filtered={stats?.last_run_easy_skipped ?? 0} scanning={running && stats?.live_found > 0} onClick={() => navigate('/jobs')} />
        <Card title="External"       value={stats?.last_run_external  } sub="no Easy Apply — open manually"                   icon={Globe2}  color="#a78bfa" onClick={() => navigate('/jobs')} />
        <Card title="Failed"         value={stats?.last_run_failed    } sub="Easy Apply errored — see Job Explorer for reason" icon={XCircle} color="#ef4444" onClick={() => navigate('/jobs')} />
        <Card title="Pending Review" value={stats?.last_run_pending   } sub={`${stats?.pending_questions ?? 0} questions · ${stats?.pending_verify ?? 0} to verify`} icon={Clock} color="#f59e0b" onClick={() => navigate('/pending')} />
      </div>

      <div className="card" style={{ marginBottom:22, display:'flex', alignItems:'flex-start', gap:12, flexWrap:'wrap' }}>
        <div style={{ height:36, width:36, borderRadius:12, background:'rgba(37,99,235,.10)', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0 }}>
          <Brain size={17} style={{ color:'#2563eb' }} />
        </div>
        <div style={{ flex:1, minWidth:260 }}>
          <div style={{ fontSize:14, fontWeight:800, color:'var(--text)', marginBottom:4 }}>Last-run decision summary</div>
          <div style={{ fontSize:13, color:'var(--text-muted)', lineHeight:1.6 }}>
            Scanned <strong>{stats?.last_run_found ?? 0}</strong> jobs, matched <strong>{stats?.last_run_matched ?? 0}</strong>,
            kept <strong>{stats?.last_run_external ?? 0}</strong> external jobs, and found <strong>{stats?.last_run_easy_skipped ?? 0}</strong> Easy Apply jobs below the current threshold.
          </div>
        </div>
        <button onClick={() => navigate('/jobs')} className="btn-secondary" style={{ whiteSpace:'nowrap' }}>
          Review decisions
        </button>
      </div>

      {/* ── TODAY section ──────────────────────────────────────── */}
      {/* Order matches Last Run: Jobs Found → Applied → External → Failed → All Time */}
      <SectionLabel tag="Today" tagColor="#a78bfa" label="Totals across all runs since midnight" />
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(190px,1fr))', gap:12, marginBottom:24 }}>
        <Card title="Matched Jobs" value={stats?.today_matched} sub={`from ${stats?.today_scanned ?? 0} scanned today`} icon={Layers3}  color="#3b82f6" onClick={() => navigate('/jobs')} />
        <AppliedCard byApp={stats?.today_applied} already={stats?.already_applied} onClick={() => navigate('/history')} />
        <Card title="External"    value={stats?.today_external} sub="no Easy Apply — open manually"         icon={Globe2}   color="#a78bfa" onClick={() => navigate('/jobs')} />
        <Card title="Failed"      value={stats?.today_failed  } sub="apply errors today — see Job Explorer" icon={XCircle}  color="#ef4444" onClick={() => navigate('/jobs')} />
      </div>

      {/* ── Inline Automation Log Panel ── */}
      <div style={{ marginBottom:24 }}>
        <AutomationPanel running={running} onStop={handleStop} onRefresh={refresh} />
      </div>

      {/* Chart */}
      <div style={{ marginBottom:24 }}>
        <HourlyChart jobs={jobs} />
      </div>

      {/* Caps strip */}
      <div className="card" style={{ marginBottom:20, display:'flex', alignItems:'center', justifyContent:'space-between', flexWrap:'wrap', gap:12 }}>
        <div style={{ fontSize:12, color:'#64748b' }}>
          <strong style={{ color:'var(--text)' }}>This hour:</strong> {stats?.hour_count ?? 0} applied  &nbsp;·&nbsp;
          <strong style={{ color:'var(--text)' }}>Today:</strong> {stats?.today_count ?? 0} applied
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:12 }}>
          <span style={{ fontSize:11, color:'#475569' }}>
            No application caps — already-applied jobs are remembered and skipped.
          </span>
          <button onClick={handleClear} disabled={clearing} title="Wipe discovered jobs and counters"
            style={{ display:'flex', alignItems:'center', gap:6, padding:'7px 12px', borderRadius:10, border:'1px solid rgba(148,163,184,.18)', background:'rgba(148,163,184,.06)', color:'#94a3b8', fontSize:12, cursor:'pointer' }}>
            <Trash2 size={12} /> {clearing ? 'Clearing…' : 'Clear jobs'}
          </button>
        </div>
      </div>
    </div>
  )
}
