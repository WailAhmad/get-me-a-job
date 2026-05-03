/**
 * AutomationPanel — inline log panel that embeds directly into the dashboard.
 * Replaces the floating AutomationWindow modal.
 */
import { useState, useEffect, useRef } from 'react'

const LEVEL_STYLE = {
  info:     { color:'#94a3b8', icon:'•',  bg:'transparent' },
  success:  { color:'#34d399', icon:'✓',  bg:'rgba(52,211,153,0.04)' },
  match:    { color:'#38bdf8', icon:'↗',  bg:'rgba(56,189,248,0.04)' },
  skip:     { color:'#64748b', icon:'–',  bg:'transparent' },
  warn:     { color:'#f87171', icon:'⚠',  bg:'rgba(239,68,68,0.03)' },
  pending:  { color:'#fbbf24', icon:'⏸',  bg:'rgba(245,158,11,0.035)' },
  external: { color:'#c4b5fd', icon:'🌐', bg:'transparent' },
}

export default function AutomationPanel({ running, onStop, onRefresh }) {
  const [logs,  setLogs]  = useState([])
  const [stats, setStats] = useState({ applied:0, skipped:0, pending:0, external:0 })
  const [runs,  setRuns]  = useState([])
  const [viewingRun, setViewingRun] = useState(null)
  const [showRuns, setShowRuns] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  const bottomRef = useRef(null)
  const logRef = useRef(null)
  const sinceRef  = useRef(0)

  const loadRuns = async () => {
    try {
      const r = await fetch('/api/automation/runs')
      const d = await r.json()
      setRuns(d.runs || [])
    } catch {}
  }

  useEffect(() => { loadRuns() }, [])

  // Poll for new logs
  useEffect(() => {
    if (!running && !viewingRun) return
    if (viewingRun) return  // don't poll when viewing a past run

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
        if (!d.running) {
          clearInterval(id)
          // Auto-save the run
          try { await fetch('/api/automation/archive-current', { method:'POST' }) } catch {}
          await loadRuns()
          if (onRefresh) onRefresh()
        }
      } catch {}
    }, 800)
    return () => clearInterval(id)
  }, [running, viewingRun])

  // Auto-scroll
  useEffect(() => {
    if (!logRef.current || collapsed) return
    logRef.current.scrollTo({ top: logRef.current.scrollHeight, behavior:'smooth' })
  }, [logs])

  // Reset logs when a new run starts
  useEffect(() => {
    if (running) {
      setLogs([])
      sinceRef.current = 0
      setViewingRun(null)
    }
  }, [running])

  const openRun = (run) => {
    setViewingRun(run)
    setLogs(run.logs || [])
    setStats({
      applied: run.summary?.verified_applied || 0,
      skipped: run.summary?.skipped || 0,
      pending: run.summary?.pending || 0,
      external: run.summary?.external || 0,
    })
    setShowRuns(false)
  }

  const isActive = running || logs.length > 0

  if (!isActive && runs.length === 0) return null

  return (
    <div style={{
      borderRadius: 18, overflow: 'hidden',
      background: '#0d1117',
      border: `1px solid ${running ? 'rgba(52,211,153,0.2)' : 'rgba(255,255,255,0.07)'}`,
      transition: 'border-color .3s',
      maxHeight: collapsed ? 72 : 560,
    }}>
      {/* ── Header ── */}
      <div style={{
        padding: '14px 18px',
        borderBottom: '1px solid rgba(255,255,255,0.06)',
        display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
      }}>
        {running ? (
          <span style={{ width:10, height:10, borderRadius:'50%', background:'#22c55e', boxShadow:'0 0 8px #22c55e', animation:'pulse 1.5s ease-in-out infinite', flexShrink:0 }} />
        ) : (
          <span style={{ width:10, height:10, borderRadius:'50%', background:'#475569', flexShrink:0 }} />
        )}
        <div style={{ flex:1 }}>
          <div style={{ fontSize:14, fontWeight:700, color:'#f1f5f9' }}>
            {running ? 'Automation Running…' : viewingRun ? `Run from ${new Date(viewingRun.started_at * 1000).toLocaleTimeString()}` : 'Last Run Complete'}
          </div>
          <div style={{ fontSize:11, color:'#475569', marginTop:1 }}>
            {running
              ? 'Discovering, scoring, and auto-applying to matching jobs'
              : viewingRun ? viewingRun.status : 'Review results below'
            }
          </div>
        </div>

        {/* Stat pills */}
        <div style={{ display:'flex', gap:5, flexWrap:'wrap' }}>
          <span style={{ fontSize:10, fontWeight:600, color:'#34d399', background:'rgba(52,211,153,0.1)', border:'1px solid rgba(52,211,153,0.2)', borderRadius:7, padding:'2px 8px' }}>✓ {stats.applied} applied</span>
          <span style={{ fontSize:10, fontWeight:600, color:'#a78bfa', background:'rgba(167,139,250,0.1)', border:'1px solid rgba(167,139,250,0.2)', borderRadius:7, padding:'2px 8px' }}>🌐 {stats.external} external</span>
          <span style={{ fontSize:10, fontWeight:600, color:'#fbbf24', background:'rgba(245,158,11,0.1)', border:'1px solid rgba(245,158,11,0.2)', borderRadius:7, padding:'2px 8px' }}>⏸ {stats.pending} pending</span>
          <span style={{ fontSize:10, fontWeight:600, color:'#64748b', background:'rgba(148,163,184,0.08)', border:'1px solid rgba(148,163,184,0.15)', borderRadius:7, padding:'2px 8px' }}>– {stats.skipped} skipped</span>
        </div>

        {running && (
          <button onClick={onStop} style={{ padding:'5px 12px', borderRadius:8, border:'1px solid rgba(239,68,68,0.3)', background:'rgba(239,68,68,0.08)', color:'#f87171', fontSize:12, fontWeight:600, cursor:'pointer' }}>
            Stop
          </button>
        )}
        <button onClick={() => setCollapsed(v => !v)} style={{ padding:'5px 10px', borderRadius:8, border:'1px solid rgba(255,255,255,0.08)', background:'rgba(255,255,255,0.04)', color:'#94a3b8', fontSize:11, cursor:'pointer' }}>
          {collapsed ? 'Expand Log' : 'Hide Log'}
        </button>
        {runs.length > 0 && (
          <button onClick={() => setShowRuns(v => !v)} style={{ padding:'5px 10px', borderRadius:8, border:'1px solid rgba(255,255,255,0.08)', background:'rgba(255,255,255,0.04)', color:'#94a3b8', fontSize:11, cursor:'pointer' }}>
            {showRuns ? 'Hide Runs' : `Previous Runs (${runs.length})`}
          </button>
        )}
      </div>

      {/* ── Previous Runs dropdown ── */}
      {!collapsed && showRuns && (
        <div style={{ padding:'10px 18px', borderBottom:'1px solid rgba(255,255,255,0.06)', background:'rgba(255,255,255,0.015)', display:'flex', gap:8, overflowX:'auto' }}>
          {runs.map(run => (
            <button key={run.id} onClick={() => openRun(run)} style={{
              flexShrink:0, textAlign:'left', padding:'8px 12px', borderRadius:10,
              background:'rgba(255,255,255,.035)', border:'1px solid rgba(255,255,255,.07)',
              cursor:'pointer', minWidth:140,
            }}>
              <div style={{ fontSize:11, fontWeight:700, color:'#f1f5f9' }}>{new Date(run.started_at * 1000).toLocaleTimeString()}</div>
              <div style={{ fontSize:10, color:'#64748b', marginTop:2 }}>
                Applied {run.summary?.verified_applied || 0} · External {run.summary?.external || 0} · Skipped {run.summary?.skipped || 0}
              </div>
            </button>
          ))}
        </div>
      )}

      {/* ── Log stream ── */}
      {!collapsed && <div ref={logRef} style={{
        height: running ? 320 : 220,
        maxHeight: '42vh',
        minHeight: 160,
        overflowY: 'auto', padding: '12px 18px',
        display: 'flex', flexDirection: 'column', gap: 3,
        overscrollBehavior: 'contain',
      }}>
        {logs.length === 0 && (
          <div style={{ color:'#334155', fontSize:13, textAlign:'center', padding:'40px 0' }}>
            {running ? 'Starting automation…' : 'No logs yet. Run automation to see activity.'}
          </div>
        )}
        {logs.map((log, i) => {
          const s = LEVEL_STYLE[log.level] || LEVEL_STYLE.info
          return (
            <div key={i} style={{
              display:'flex', alignItems:'flex-start', gap:8,
              padding:'5px 8px', borderRadius:8, background:s.bg,
            }}>
              <span style={{ fontSize:12, color:s.color, fontWeight:700, flexShrink:0, marginTop:1, width:16, textAlign:'center' }}>{s.icon}</span>
              <span style={{ fontSize:12, color:s.color, lineHeight:1.5, overflowWrap:'anywhere' }}>{log.msg}</span>
            </div>
          )
        })}
        {running && (
          <div style={{ display:'flex', alignItems:'center', gap:8, padding:'5px 8px', color:'#475569', fontSize:12 }}>
            <svg style={{ width:14, height:14, animation:'spin 1s linear infinite', flexShrink:0 }} viewBox="0 0 24 24" fill="none">
              <circle opacity=".25" cx="12" cy="12" r="10" stroke="#64748b" strokeWidth="4"/>
              <path opacity=".75" fill="#64748b" d="M4 12a8 8 0 018-8v8H4z"/>
            </svg>
            Processing jobs…
          </div>
        )}
        {!running && logs.length > 0 && (
          <div style={{ marginTop:8, textAlign:'center', padding:'10px', borderRadius:12, background:'rgba(52,211,153,0.05)', border:'1px solid rgba(52,211,153,0.12)' }}>
            <div style={{ fontSize:13, fontWeight:700, color:'#34d399' }}>Session complete</div>
            <div style={{ fontSize:11, color:'#64748b', marginTop:2 }}>Applied {stats.applied} · External {stats.external} · Skipped {stats.skipped}</div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>}
    </div>
  )
}
