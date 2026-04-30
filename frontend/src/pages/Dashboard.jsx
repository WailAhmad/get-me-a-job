import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getDashboardStats, getAutomationStatus, stopAutomation, startAutomation, clearJobs, getJobs, getLiveMode } from '../api/client'
import { Briefcase, CheckCircle, Clock, Globe2, Play, Square, Radio, FileText, MessageSquare, AlertTriangle, ShieldAlert, Layers3, Trash2, MinusCircle, ListChecks } from 'lucide-react'
import AutomationWindow from '../components/AutomationWindow'
import HourlyChart from '../components/HourlyChart'

const Card = ({ title, value, sub, icon:Icon, color, onClick, accent }) => (
  <button onClick={onClick}
    style={{
      textAlign:'left', cursor: onClick?'pointer':'default',
      background:'rgba(255,255,255,0.03)',
      border:`1px solid ${accent ? color+'40' : 'rgba(255,255,255,0.07)'}`,
      borderRadius:18, padding:18, position:'relative', overflow:'hidden',
      transition:'all .2s', width:'100%',
    }}
    onMouseEnter={e => { if(onClick){ e.currentTarget.style.borderColor = color+'66'; e.currentTarget.style.transform='translateY(-1px)' } }}
    onMouseLeave={e => { e.currentTarget.style.borderColor = accent ? color+'40' : 'rgba(255,255,255,0.07)'; e.currentTarget.style.transform='translateY(0)' }}
  >
    <div style={{ position:'absolute', right:-14, top:-14, height:60, width:60, borderRadius:'50%', background:color+'14', filter:'blur(2px)' }} />
    <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:10 }}>
      <div style={{ height:32, width:32, borderRadius:10, background:color+'18', display:'flex', alignItems:'center', justifyContent:'center' }}>
        <Icon size={15} style={{ color }} />
      </div>
      <div style={{ fontSize:11, fontWeight:600, color:'#94a3b8', textTransform:'uppercase', letterSpacing:'.06em' }}>{title}</div>
    </div>
    <div style={{ fontSize:30, fontWeight:800, color:'#f8fafc', lineHeight:1 }}>{value}</div>
    {sub && <div style={{ fontSize:11, color:'#64748b', marginTop:6 }}>{sub}</div>}
  </button>
)

export default function Dashboard({ cv, prefs, onRefresh }) {
  const navigate = useNavigate()
  const [stats,    setStats]    = useState(null)
  const [jobs,     setJobs]     = useState([])
  const [running,  setRunning]  = useState(false)
  const [busy,     setBusy]     = useState(false)
  const [clearing, setClearing] = useState(false)
  const [showLogs, setShowLogs] = useState(false)
  const [error,    setError]    = useState('')
  const [liveMode, setLiveModeState] = useState({ live_mode:false, linkedin_session:false, effective:false })

  const refresh = async () => {
    try { setStats(await getDashboardStats()) } catch {}
    try { const s = await getAutomationStatus(); setRunning(s?.running ?? false) } catch {}
    try { setJobs(await getJobs()) } catch {}
    try { setLiveModeState(await getLiveMode()) } catch {}
  }

  useEffect(() => { refresh(); const id = setInterval(refresh, 5000); return () => clearInterval(id) }, [])

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
      else { setShowLogs(true); setRunning(true) }
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
  const canRun  = cvOK && prefsOK

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:24, flexWrap:'wrap', gap:12 }}>
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-subtitle">Your 24/7 LinkedIn application autopilot</p>
        </div>
        <div style={{ display:'flex', gap:10 }}>
          {running ? (
            <>
              <button onClick={() => setShowLogs(true)} style={{ display:'flex', alignItems:'center', gap:7, padding:'9px 16px', borderRadius:12, border:'1px solid rgba(56,189,248,0.3)', background:'rgba(56,189,248,0.08)', color:'#38bdf8', fontSize:13, fontWeight:600, cursor:'pointer' }}>
                <Radio size={13} /> Watch Live
              </button>
              <button onClick={handleStop} disabled={busy} style={{ display:'flex', alignItems:'center', gap:7, padding:'9px 16px', borderRadius:12, border:'1px solid rgba(239,68,68,0.25)', background:'rgba(239,68,68,0.07)', color:'#f87171', fontSize:13, fontWeight:600, cursor:'pointer' }}>
                <Square size={13} /> {busy ? 'Stopping…' : 'Stop'}
              </button>
            </>
          ) : (
            <button
              onClick={canRun ? handleStart : () => navigate(cvOK ? '/chat' : '/cv')}
              disabled={busy}
              className="btn-primary"
              style={{ gap:8, opacity: canRun ? 1 : 0.6 }}
              title={canRun ? '' : (cvOK ? 'Set preferences in AI Assistant' : 'Upload your CV first')}
            >
              <Play size={13} /> {canRun ? 'Run Automation' : (cvOK ? 'Set Preferences →' : 'Upload CV →')}
            </button>
          )}
        </div>
      </div>

      {/* Live / demo banner */}
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
            {liveMode.effective ? 'LIVE MODE — real LinkedIn submissions' : 'DEMO MODE — no real submissions'}
          </div>
          <div style={{ fontSize:11, color:'#94a3b8', marginTop:1 }}>
            {liveMode.effective
              ? 'Automation drives a real Selenium browser using your saved LinkedIn session. Daily cap 100, hourly 10.'
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
            { n:'2', title:'Chat with AI Assistant',   desc:'Set country, recency, and target roles in natural language.',           color:'#14b8a6' },
            { n:'3', title:'Run Automation',           desc:'We auto-apply to Easy Apply matches and route the rest to External / Pending.',  color:'#a78bfa' },
          ].map((s, i) => (
            <div key={i} style={{ flex:'1 1 220px', display:'flex', alignItems:'flex-start', gap:12, padding:'0 16px', borderRight: i<2 ? '1px solid rgba(255,255,255,0.06)' : 'none' }}>
              <div style={{ width:28, height:28, borderRadius:8, background:`${s.color}18`, border:`1px solid ${s.color}30`, display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0, fontSize:12, fontWeight:700, color:s.color }}>{s.n}</div>
              <div>
                <div style={{ fontSize:13, fontWeight:600, color:'#e2e8f0', marginBottom:4 }}>{s.title}</div>
                <div style={{ fontSize:12, color:'#475569', lineHeight:1.6 }}>{s.desc}</div>
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
              <div style={{ fontSize:14, fontWeight:600, color:'#fbbf24' }}>Finish setting up before automation can run</div>
              <div style={{ fontSize:12, color:'#94a3b8', marginTop:2 }}>Two quick steps stand between you and 24/7 auto-apply.</div>
            </div>
          </div>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
            <button onClick={() => navigate('/cv')} style={{ textAlign:'left', display:'flex', gap:12, alignItems:'center', padding:14, borderRadius:14, border:`1px solid ${cvOK?'rgba(16,185,129,0.25)':'rgba(59,130,246,0.25)'}`, background:cvOK?'rgba(16,185,129,0.06)':'rgba(59,130,246,0.06)', cursor:'pointer' }}>
              <div style={{ height:36, width:36, borderRadius:10, background: cvOK?'rgba(16,185,129,0.16)':'rgba(59,130,246,0.16)', display:'flex', alignItems:'center', justifyContent:'center' }}>
                {cvOK ? <CheckCircle size={16} style={{ color:'#34d399' }} /> : <FileText size={16} style={{ color:'#60a5fa' }} />}
              </div>
              <div>
                <div style={{ fontSize:13, fontWeight:600, color:'#f1f5f9' }}>1. {cvOK ? 'CV uploaded' : 'Upload your CV'}</div>
                <div style={{ fontSize:11, color:'#64748b', marginTop:2 }}>{cvOK ? `${cv.skills?.length||0} skills · ${cv.years||0} years` : 'PDF or DOCX — used to match jobs'}</div>
              </div>
            </button>
            <button onClick={() => navigate('/chat')} disabled={!cvOK} style={{ textAlign:'left', display:'flex', gap:12, alignItems:'center', padding:14, borderRadius:14, border:`1px solid ${prefsOK?'rgba(16,185,129,0.25)':'rgba(20,184,166,0.25)'}`, background:prefsOK?'rgba(16,185,129,0.06)':'rgba(20,184,166,0.06)', cursor:cvOK?'pointer':'not-allowed', opacity:cvOK?1:0.5 }}>
              <div style={{ height:36, width:36, borderRadius:10, background: prefsOK?'rgba(16,185,129,0.16)':'rgba(20,184,166,0.16)', display:'flex', alignItems:'center', justifyContent:'center' }}>
                {prefsOK ? <CheckCircle size={16} style={{ color:'#34d399' }} /> : <MessageSquare size={16} style={{ color:'#2dd4bf' }} />}
              </div>
              <div>
                <div style={{ fontSize:13, fontWeight:600, color:'#f1f5f9' }}>2. {prefsOK ? 'Preferences set' : 'Chat with AI Assistant'}</div>
                <div style={{ fontSize:11, color:'#64748b', marginTop:2 }}>{prefsOK ? `${prefs.country} · last ${prefs.recency_days} days` : 'Country, recency, target roles'}</div>
              </div>
            </button>
          </div>
        </div>
      )}

      {error && (
        <div style={{ background:'rgba(239,68,68,.08)', border:'1px solid rgba(239,68,68,.2)', borderRadius:12, padding:'10px 14px', fontSize:12, color:'#fca5a5', marginBottom:14 }}>{error}</div>
      )}

      {/* Running banner */}
      {running && (
        <div style={{ display:'flex', alignItems:'center', gap:10, background:'rgba(16,185,129,.07)', border:'1px solid rgba(16,185,129,.18)', borderRadius:14, padding:'12px 16px', marginBottom:20, cursor:'pointer' }} onClick={() => setShowLogs(true)}>
          <span style={{ width:8, height:8, borderRadius:'50%', background:'#10b981', boxShadow:'0 0 6px #10b981', animation:'pulse 1.5s ease-in-out infinite', flexShrink:0 }} />
          <span style={{ fontSize:13, color:'#34d399', flex:1 }}>Automation is running — scanning and applying to LinkedIn jobs</span>
          <span style={{ fontSize:12, color:'#0ea5e9', fontWeight:600 }}>Watch Live →</span>
        </div>
      )}

      {/* Primary cards */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(210px,1fr))', gap:14, marginBottom:14 }}>
        <Card title="Jobs Found"        value={stats?.jobs_found     ?? '—'} sub="total discovered across all sources"  icon={Layers3}    color="#3b82f6" onClick={() => navigate('/jobs')} />
        <Card title="Verified Applied"  value={stats?.auto_applied   ?? '—'} sub={`${stats?.applied_today ?? 0} today · cap ${stats?.daily_cap ?? 100}/day`} icon={CheckCircle} color="#10b981" accent onClick={() => navigate('/history')} />
        <Card title="External Jobs"     value={stats?.external_jobs  ?? '—'} sub="not Easy Apply — open & apply manually" icon={Globe2}    color="#a78bfa" onClick={() => navigate('/jobs')} />
        <Card title="Pending Review"    value={stats?.pending        ?? '—'} sub={`${stats?.pending_questions ?? 0} questions · ${stats?.pending_verify ?? 0} verify`} icon={Clock} color="#f59e0b" onClick={() => navigate('/pending')} />
      </div>

      {/* Secondary cards */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(210px,1fr))', gap:14, marginBottom:24 }}>
        <Card title="Skipped"           value={stats?.skipped        ?? '—'} sub="match score below 60%"                icon={MinusCircle} color="#64748b" onClick={() => navigate('/jobs')} />
        <Card title="Recorded (unverified)" value={stats?.recorded_applications ?? '—'} sub="legacy actions that still need verification" icon={ShieldAlert} color="#fbbf24" onClick={() => navigate('/history')} />
        <Card title="Queued"            value={stats?.queued         ?? '—'} sub="discovered, not yet processed"         icon={ListChecks} color="#0ea5e9" onClick={() => navigate('/jobs')} />
        <Card title="Applied Today"     value={stats?.applied_today  ?? '—'} sub={`this hour: ${stats?.hour_count ?? 0}/${stats?.hourly_cap ?? 10}`} icon={Briefcase} color="#34d399" onClick={() => navigate('/history')} />
      </div>

      {/* Chart */}
      <div style={{ marginBottom:24 }}>
        <HourlyChart jobs={jobs} />
      </div>

      {/* Caps strip */}
      <div className="card" style={{ marginBottom:20, display:'flex', alignItems:'center', justifyContent:'space-between', flexWrap:'wrap', gap:12 }}>
        <div style={{ fontSize:12, color:'#64748b' }}>
          <strong style={{ color:'#cbd5e1' }}>This hour:</strong> {stats?.hour_count ?? 0} / {stats?.hourly_cap ?? 10}  &nbsp;·&nbsp;
          <strong style={{ color:'#cbd5e1' }}>Today:</strong> {stats?.today_count ?? 0} / {stats?.daily_cap ?? 100}
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:12 }}>
          <span style={{ fontSize:11, color:'#475569' }}>
            Max 10 auto-applies per hour · 100 per day · already-applied jobs are remembered.
          </span>
          <button onClick={handleClear} disabled={clearing} title="Wipe discovered jobs and counters"
            style={{ display:'flex', alignItems:'center', gap:6, padding:'7px 12px', borderRadius:10, border:'1px solid rgba(148,163,184,.18)', background:'rgba(148,163,184,.06)', color:'#94a3b8', fontSize:12, cursor:'pointer' }}>
            <Trash2 size={12} /> {clearing ? 'Clearing…' : 'Clear jobs'}
          </button>
        </div>
      </div>

      {showLogs && <AutomationWindow onClose={() => { setShowLogs(false); refresh(); onRefresh && onRefresh() }} alreadyRunning={running} />}
    </div>
  )
}
