import { useState, useEffect, useRef } from 'react'

const LEVEL_STYLE = {
  info:     { color:'#94a3b8', icon:'•' },
  success:  { color:'#34d399', icon:'✓' },
  match:    { color:'#38bdf8', icon:'↗' },
  skip:     { color:'#94a3b8', icon:'–' },
  warn:     { color:'#f87171', icon:'!' },
  pending:  { color:'#fbbf24', icon:'⏸' },
  external: { color:'#c4b5fd', icon:'🌐' },
}

export default function AutomationWindow({ onClose, alreadyRunning }) {
  const [logs,    setLogs]    = useState([])
  const [running, setRunning] = useState(true)
  const [started] = useState(true)
  const [stats,   setStats]   = useState({ applied:0, skipped:0, pending:0, external:0 })
  const [expanded, setExpanded] = useState(false)
  const [runs, setRuns] = useState([])
  const [saved, setSaved] = useState(false)
  const bottomRef = useRef(null)
  const sinceRef  = useRef(0)

  const loadRuns = async () => {
    try {
      const r = await fetch('/api/automation/runs')
      const d = await r.json()
      setRuns(d.runs || [])
    } catch {}
  }

  useEffect(() => { loadRuns() }, [])

  // poll for new logs every 800ms
  useEffect(() => {
    if (!started) return
    const id = setInterval(async () => {
      try {
        const r = await fetch(`/api/automation/logs/poll?since=${sinceRef.current}`)
        const d = await r.json()
        if (d.logs.length) {
          sinceRef.current = d.logs[d.logs.length - 1].ts
          setLogs(prev => {
            const next = [...prev, ...d.logs]
            let a = 0, s = 0, p = 0, e = 0
            next.forEach(l => {
              if (l.level === 'success' && /Applied/i.test(l.msg)) a++
              if (l.level === 'skip')     s++
              if (l.level === 'pending')  p++
              if (l.level === 'external') e++
            })
            setStats({ applied:a, skipped:s, pending:p, external:e })
            return next
          })
        }
        if (!d.running) { setRunning(false); clearInterval(id) }
      } catch {}
    }, 800)
    return () => clearInterval(id)
  }, [started])

  // auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior:'smooth' })
  }, [logs])

  const handleStop = async () => {
    await fetch('/api/automation/stop', { method:'POST' })
    setRunning(false)
    await loadRuns()
  }

  const saveRun = async () => {
    try {
      await fetch('/api/automation/archive-current', { method:'POST' })
      setSaved(true)
      await loadRuns()
    } catch {}
  }

  useEffect(() => {
    if (!running && logs.length && !saved) saveRun()
  }, [running, logs.length, saved])

  const openRun = (run) => {
    setLogs(run.logs || [])
    setStats({
      applied: run.summary?.verified_applied || 0,
      skipped: run.summary?.skipped || 0,
      pending: run.summary?.pending || 0,
      external: run.summary?.external || 0,
    })
    setRunning(false)
    setSaved(true)
  }

  return (
    <div style={{
      position:'fixed', inset:0, zIndex:1000,
      background:'rgba(0,0,0,0.62)', backdropFilter:'blur(6px)',
      display:'flex', alignItems:'center', justifyContent:'center',
      padding:18, fontFamily:"'Inter',system-ui,sans-serif"
    }}>
      <div style={{
        width:'100%', maxWidth:expanded ? 1120 : 820, borderRadius:22,
        background:'#0d1117', border:'1px solid rgba(255,255,255,0.08)',
        boxShadow:'0 32px 80px rgba(0,0,0,0.7)',
        display:'flex', flexDirection:'column', height:expanded ? '92vh' : '82vh', maxHeight:'92vh', overflow:'hidden',
        transition:'max-width .2s ease, height .2s ease'
      }}>
        {/* ── Header ── */}
        <div style={{ padding:'16px 18px', borderBottom:'1px solid rgba(255,255,255,0.06)', display:'flex', alignItems:'center', gap:12, flexWrap:'wrap' }}>
          {running ? (
            <span style={{ width:10, height:10, borderRadius:'50%', background:'#22c55e', display:'inline-block', boxShadow:'0 0 8px #22c55e', animation:'pulse 1.5s ease-in-out infinite', flexShrink:0 }} />
          ) : (
            <span style={{ width:10, height:10, borderRadius:'50%', background:'#475569', display:'inline-block', flexShrink:0 }} />
          )}
          <div style={{ flex:1 }}>
            <div style={{ fontSize:15, fontWeight:800, color:'var(--text)' }}>
              {running ? 'Automation Running…' : 'Automation Complete'}
            </div>
            <div style={{ fontSize:11, color:'#475569', marginTop:2 }}>
              Discovery, scoring, and verified-apply preparation
            </div>
          </div>
          {/* stat pills */}
          <div style={{ display:'flex', gap:6, flexWrap:'wrap', justifyContent:'flex-end' }}>
            <span style={{ fontSize:11, fontWeight:600, color:'#34d399', background:'rgba(52,211,153,0.1)', border:'1px solid rgba(52,211,153,0.2)', borderRadius:8, padding:'3px 10px' }}>✓ {stats.applied} verified applied</span>
            <span style={{ fontSize:11, fontWeight:600, color:'#a78bfa', background:'rgba(167,139,250,0.1)', border:'1px solid rgba(167,139,250,0.2)', borderRadius:8, padding:'3px 10px' }}>🌐 {stats.external} external</span>
            <span style={{ fontSize:11, fontWeight:600, color:'#fbbf24', background:'rgba(245,158,11,0.1)', border:'1px solid rgba(245,158,11,0.2)', borderRadius:8, padding:'3px 10px' }}>⏸ {stats.pending} pending</span>
            <span style={{ fontSize:11, fontWeight:600, color:'#94a3b8', background:'rgba(148,163,184,0.08)', border:'1px solid rgba(148,163,184,0.18)', borderRadius:8, padding:'3px 10px' }}>– {stats.skipped} skipped</span>
          </div>
          {running && (
            <button onClick={handleStop} style={{ padding:'6px 14px', borderRadius:10, border:'1px solid rgba(239,68,68,0.3)', background:'rgba(239,68,68,0.08)', color:'#f87171', fontSize:12, fontWeight:600, cursor:'pointer' }}>
              Stop
            </button>
          )}
          <button onClick={() => setExpanded(v => !v)} style={{ padding:'6px 10px', borderRadius:10, border:'1px solid rgba(255,255,255,0.08)', background:'rgba(255,255,255,0.04)', color:'#94a3b8', fontSize:12, cursor:'pointer' }}>
            {expanded ? 'Compact' : 'Expand'}
          </button>
          <button onClick={onClose} aria-label="Close run window" style={{ padding:'6px 10px', borderRadius:10, border:'1px solid var(--border)', background:'var(--bg-subtle)', color:'var(--text)', fontSize:14, cursor:'pointer' }}>Close</button>
        </div>

        <div style={{ flex:1, minHeight:0, display:'grid', gridTemplateColumns:expanded ? '1fr 280px' : '1fr', overflow:'hidden' }}>
          {/* ── Log stream ── */}
          <div style={{ minHeight:0, overflowY:'auto', padding:'16px 18px', display:'flex', flexDirection:'column', gap:6 }}>
            {logs.length === 0 && (
              <div style={{ color:'#334155', fontSize:13, textAlign:'center', marginTop:40 }}>
                Starting automation…
              </div>
            )}
            {logs.map((log, i) => {
              const s = LEVEL_STYLE[log.level] || LEVEL_STYLE.info
              return (
                <div key={i} style={{ display:'flex', alignItems:'flex-start', gap:10, padding:'8px 10px', borderRadius:12, background: log.level==='success'?'rgba(52,211,153,0.04)' : log.level==='match'?'rgba(56,189,248,0.04)' : log.level==='pending'?'rgba(245,158,11,0.035)' : 'transparent', transition:'background .3s' }}>
                  <span style={{ fontSize:13, color:s.color, fontWeight:700, flexShrink:0, marginTop:1 }}>{s.icon}</span>
                  <span style={{ fontSize:13, color:s.color, lineHeight:1.55, overflowWrap:'anywhere' }}>{log.msg}</span>
                </div>
              )
            })}
            {running && (
              <div style={{ display:'flex', alignItems:'center', gap:8, padding:'7px 10px', color:'#334155', fontSize:12 }}>
                <svg style={{ width:14, height:14, animation:'spin 1s linear infinite', flexShrink:0 }} viewBox="0 0 24 24" fill="none">
                  <circle opacity=".25" cx="12" cy="12" r="10" stroke="#64748b" strokeWidth="4"/>
                  <path opacity=".75" fill="#64748b" d="M4 12a8 8 0 018-8v8H4z"/>
                </svg>
                Scanning next batch…
              </div>
            )}
            {!running && logs.length > 0 && (
              <div style={{ marginTop:16, textAlign:'center', padding:'14px', borderRadius:14, background:'rgba(52,211,153,0.06)', border:'1px solid rgba(52,211,153,0.15)' }}>
                <div style={{ fontSize:14, fontWeight:700, color:'#34d399' }}>Session complete</div>
                <div style={{ fontSize:12, color:'#64748b', marginTop:4 }}>Run saved to Previous Runs. Review candidates in Job Explorer.</div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {expanded && (
            <aside style={{ borderLeft:'1px solid rgba(255,255,255,0.06)', background:'rgba(255,255,255,0.025)', padding:14, overflowY:'auto' }}>
              <div style={{ fontSize:12, fontWeight:700, color:'#94a3b8', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:10 }}>Previous Runs</div>
              {runs.length === 0 ? (
                <p style={{ fontSize:12, color:'#475569', lineHeight:1.5 }}>Completed runs will be saved here.</p>
              ) : runs.map(run => (
                <button key={run.id} onClick={() => openRun(run)} style={{ width:'100%', textAlign:'left', background:'rgba(255,255,255,.035)', border:'1px solid rgba(255,255,255,.07)', borderRadius:14, padding:12, marginBottom:10, cursor:'pointer' }}>
                  <div style={{ display:'flex', justifyContent:'space-between', gap:8, marginBottom:6 }}>
                    <span style={{ fontSize:13, fontWeight:700, color:'var(--text)' }}>{new Date(run.started_at * 1000).toLocaleTimeString()}</span>
                    <span className="badge badge-blue" style={{ fontSize:10 }}>{run.status}</span>
                  </div>
                  <div style={{ fontSize:11, color:'#64748b', lineHeight:1.6 }}>
                    Found {run.summary?.discovered || 0} · External {run.summary?.external || 0}<br />
                    Pending {run.summary?.pending || 0} · Skipped {run.summary?.skipped || 0}
                  </div>
                </button>
              ))}
            </aside>
          )}
        </div>

        <div style={{ borderTop:'1px solid rgba(255,255,255,0.06)', padding:'12px 16px', display:'flex', alignItems:'center', justifyContent:'space-between', gap:10, flexWrap:'wrap' }}>
          <div style={{ fontSize:12, color:'#64748b' }}>
            {running ? 'Live run in progress' : saved ? 'Completed run saved' : 'Run complete'}
          </div>
          <div style={{ display:'flex', gap:8 }}>
            {!running && (
              <button onClick={saveRun} className="btn-secondary" style={{ padding:'8px 12px', fontSize:12 }}>
                Save Run
              </button>
            )}
            <button onClick={() => setExpanded(v => !v)} className="btn-secondary" style={{ padding:'8px 12px', fontSize:12 }}>
              {expanded ? 'Hide Previous Runs' : 'Show Previous Runs'}
            </button>
            <button onClick={onClose} className="btn-primary" style={{ padding:'8px 14px', fontSize:12 }}>
              Close Window
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
