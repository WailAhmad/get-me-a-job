import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { sendChat, getChat, resetChat, startAutomation } from '../api/client'
import { Send, Bot, RefreshCw, Play, MapPin, Calendar, Briefcase, Globe, Filter, Sparkles, CheckCircle2, Search } from 'lucide-react'

function renderText(text) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g)
  return parts.map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**')) return <strong key={i} style={{ color:'var(--text)' }}>{p.slice(2,-2)}</strong>
    return <span key={i}>{p}</span>
  })
}

/* ── Filter sidebar card ──────────────────────────────────────────── */
function FilterSidebar({ prefs }) {
  const country   = prefs?.country
  const countries = prefs?.countries || (country ? [country] : [])
  const days      = prefs?.recency_days
  const keywords  = prefs?.search_keywords || []
  const roles     = prefs?.roles || []
  const ready     = prefs?.ready

  const filters = []
  if (country) {
    filters.push({ icon: MapPin,    label: 'Region',    value: country,  color: '#3b82f6', items: countries })
  }
  if (days) {
    const nice = { 1:'Past 24 hours', 7:'Last 7 days', 14:'Last 14 days', 30:'Last 30 days' }[days] || `Last ${days} days`
    filters.push({ icon: Calendar,  label: 'Recency',   value: nice,     color: '#8b5cf6' })
  }
  if (keywords.length) {
    filters.push({ icon: Search, label: 'LinkedIn Keywords', value: `${keywords.length} quer${keywords.length>1?'ies':'y'}`, color: '#14b8a6', items: keywords })
  }
  if (roles.length) {
    filters.push({ icon: Briefcase, label: 'Target Roles', value: `${roles.length} role${roles.length>1?'s':''}`, color: '#0ea5e9', items: roles })
  }
  const missing = !country ? 'region' : !days ? 'timeframe' : !roles.length ? 'target roles' : 'preferences'

  return (
    <div style={{ width: 260, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 12, height: '100%' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 4px' }}>
        <Filter size={14} style={{ color: '#64748b' }} />
        <span style={{ fontSize: 13, fontWeight: 700, color: '#94a3b8', letterSpacing: '.04em', textTransform: 'uppercase' }}>Search Filters</span>
        {ready && <CheckCircle2 size={14} style={{ color: '#34d399', marginLeft: 'auto' }} />}
      </div>

      {/* Filter cards */}
      {filters.length === 0 ? (
        <div style={{ padding: 20, textAlign: 'center', borderRadius: 16, background: 'rgba(255,255,255,0.02)', border: '1px dashed rgba(255,255,255,0.08)' }}>
          <Sparkles size={20} style={{ color: '#475569', margin: '0 auto 8px' }} />
          <div style={{ fontSize: 12, color: '#475569', lineHeight: 1.6 }}>
            Chat with <strong style={{ color: '#94a3b8' }}>Jobby</strong> to set your search filters.
            <br />Tell me your target country, timeframe, and roles.
          </div>
        </div>
      ) : (
        filters.map((f, i) => (
          <div key={i} style={{
            borderRadius: 14, padding: 14,
            background: `linear-gradient(135deg, ${f.color}08, ${f.color}04)`,
            border: `1px solid ${f.color}22`,
            transition: 'all .2s',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <div style={{
                width: 28, height: 28, borderRadius: 8,
                background: `${f.color}18`, display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <f.icon size={14} style={{ color: f.color }} />
              </div>
              <div>
                <div style={{ fontSize: 10, fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '.05em' }}>{f.label}</div>
                <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)' }}>{f.value}</div>
              </div>
            </div>
            {f.items && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
                {f.items.map((item, j) => (
                  <span key={j} style={{
                    fontSize: 11, padding: '3px 8px', borderRadius: 6,
                    background: `${f.color}12`, color: `${f.color}cc`,
                    border: `1px solid ${f.color}18`, fontWeight: 500,
                  }}>{item}</span>
                ))}
              </div>
            )}
          </div>
        ))
      )}

      {/* JSON preview */}
      {filters.length > 0 && (
        <div style={{ marginTop: 'auto' }}>
          <div style={{ fontSize: 10, fontWeight: 600, color: '#475569', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '.05em', padding: '0 4px' }}>Filter JSON</div>
          <pre style={{
            fontSize: 10, lineHeight: 1.5, color: '#64748b', padding: 12, borderRadius: 12,
            background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.06)',
            overflow: 'auto', maxHeight: 160, margin: 0, fontFamily: "'SF Mono', 'Fira Code', monospace",
          }}>
{JSON.stringify({
  region: country || null,
  locations: countries.length ? countries : null,
  recency_days: days || null,
  target_roles: roles.length ? roles : null,
  search_keywords: keywords.length ? keywords : null,
  status: ready ? 'ready' : 'incomplete',
}, null, 2)}
          </pre>
        </div>
      )}

      {/* Status indicator */}
      <div style={{
        padding: '10px 12px', borderRadius: 12,
        background: ready ? 'rgba(52,211,153,0.06)' : 'rgba(245,158,11,0.06)',
        border: `1px solid ${ready ? 'rgba(52,211,153,0.2)' : 'rgba(245,158,11,0.2)'}`,
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <div style={{
          width: 8, height: 8, borderRadius: '50%',
          background: ready ? '#34d399' : '#f59e0b',
          boxShadow: `0 0 8px ${ready ? '#34d39966' : '#f59e0b66'}`,
          animation: ready ? 'none' : 'pulse 2s infinite',
        }} />
        <span style={{ fontSize: 11, fontWeight: 600, color: ready ? '#34d399' : '#fbbf24' }}>
          {ready ? 'Filters ready — launch automation' : `Waiting for ${missing}…`}
        </span>
      </div>
    </div>
  )
}

/* ── Main Chat page ───────────────────────────────────────────────── */
export default function Chat({ cv, onPrefsUpdate }) {
  const navigate = useNavigate()
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [startingAutomation, setStartingAutomation] = useState(false)
  const [runError, setRunError] = useState('')
  const [step, setStep] = useState('greet')
  const [prefs, setPrefs] = useState(null)
  const endRef = useRef(null)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior:'smooth' }) }, [messages])

  useEffect(() => {
    (async () => {
      try {
        const r = await getChat()
        if (r.history?.length) {
          setMessages(r.history.map(m => ({ role:m.role, content:m.content })))
          setStep(r.step); setPrefs(r.preferences)
          onPrefsUpdate && onPrefsUpdate(r.preferences)
        } else {
          const g = await sendChat('')
          setMessages([{ role:'assistant', content: g.reply }])
          setStep(g.step); setPrefs(g.preferences)
          onPrefsUpdate && onPrefsUpdate(g.preferences)
        }
      } catch {}
    })()
  }, [])

  const send = async () => {
    if (!input.trim() || loading) return
    const msg = input.trim()
    setInput('')
    setMessages(m => [...m, { role:'user', content:msg }])
    setLoading(true)
    try {
      const r = await sendChat(msg)
      setMessages(m => [...m, { role:'assistant', content: r.reply }])
      setStep(r.step); setPrefs(r.preferences)
      onPrefsUpdate && onPrefsUpdate(r.preferences)
    } catch (e) {
      setMessages(m => [...m, { role:'assistant', content:`Error: ${e.message}` }])
    } finally { setLoading(false) }
  }

  const reset = async () => {
    setLoading(true)
    try {
      const r = await resetChat()
      setMessages([{ role:'assistant', content: r.reply }])
      setStep(r.step); setPrefs(r.preferences)
      onPrefsUpdate && onPrefsUpdate(r.preferences)
    } finally { setLoading(false) }
  }

  const ready = step === 'ready' && prefs?.ready
  const noCV  = !cv?.uploaded
  const suggestionChips = !ready && !noCV && step === 'recency'
    ? ['today', 'last week', 'last 14 days', 'last 30 days']
    : ready && !noCV
      ? ['add Europe', 'change to last 30 days', 'only GCC', 'add remote']
    : !ready && !noCV && step === 'country'
      ? ['GCC', 'Europe', 'Remote']
      : !ready && !noCV && step === 'roles'
        ? ['match my CV', 'Head of Data', 'AI Director']
        : []

  const sendSuggestion = async (text) => {
    if (loading) return
    setInput(text)
    const msg = text.trim()
    setMessages(m => [...m, { role:'user', content:msg }])
    setLoading(true)
    try {
      const r = await sendChat(msg)
      setMessages(m => [...m, { role:'assistant', content: r.reply }])
      setStep(r.step); setPrefs(r.preferences)
      onPrefsUpdate && onPrefsUpdate(r.preferences)
    } catch (e) {
      setMessages(m => [...m, { role:'assistant', content:`Error: ${e.message}` }])
    } finally {
      setInput('')
      setLoading(false)
    }
  }

  const runAutomation = async () => {
    if (startingAutomation) return
    setRunError('')
    setStartingAutomation(true)
    try {
      await startAutomation()
      navigate('/')
    } catch (e) {
      const detail = e?.response?.data?.detail || e.message || 'Could not start automation.'
      setRunError(detail)
    } finally {
      setStartingAutomation(false)
    }
  }

  return (
    <div style={{ display:'flex', gap: 20, height:'calc(100vh - 80px)' }}>
      {/* ── Chat column ── */}
      <div style={{ flex: 1, display:'flex', flexDirection:'column', minWidth: 0 }}>
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:16, gap:12 }}>
          <div style={{ display:'flex', alignItems:'center', gap: 10 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 12,
              background: 'linear-gradient(135deg, #6366f1, #0ea5e9)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 4px 12px rgba(99,102,241,0.3)',
            }}>
              <Sparkles size={18} style={{ color: '#fff' }} />
            </div>
            <div>
              <h1 className="page-title" style={{ margin: 0 }}>Jobby</h1>
              <p className="page-subtitle" style={{ margin: 0 }}>Your AI job search assistant</p>
            </div>
          </div>
          <button onClick={reset} disabled={loading} style={{
            display:'flex', alignItems:'center', gap:6, padding:'8px 12px', borderRadius:10,
            border:'1px solid rgba(255,255,255,0.08)', background:'rgba(255,255,255,0.03)',
            color:'#94a3b8', fontSize:12, cursor:'pointer',
          }}>
            <RefreshCw size={12} /> Reset
          </button>
        </div>

        {noCV && (
          <div className="card" style={{ marginBottom:14, background:'rgba(245,158,11,0.06)', border:'1px solid rgba(245,158,11,0.22)' }}>
            <div style={{ fontSize:13, color:'#fbbf24', marginBottom:6, fontWeight:600 }}>Upload your CV first</div>
            <div style={{ fontSize:12, color:'#94a3b8', marginBottom:10 }}>Jobby matches jobs to your real skills — upload your CV before setting preferences.</div>
            <button onClick={() => navigate('/cv')} className="btn-primary" style={{ gap:6 }}>Go to My CV →</button>
          </div>
        )}

        <div className="card" style={{ flex:1, overflowY:'auto', marginBottom:12, padding:16 }}>
          {messages.map((m,i) => (
            <div key={i} style={{ display:'flex', gap:10, marginBottom:14, justifyContent:m.role==='user'?'flex-end':'flex-start' }}>
              {m.role==='assistant' && (
                <div style={{
                  height:28, width:28, borderRadius:10, flexShrink:0,
                  background:'linear-gradient(135deg,#6366f1,#0ea5e9)',
                  display:'flex', alignItems:'center', justifyContent:'center',
                  boxShadow: '0 2px 8px rgba(99,102,241,0.25)',
                }}>
                  <Sparkles size={13} style={{ color:'#fff' }} />
                </div>
              )}
              <div style={{
                maxWidth:'78%', padding:'10px 14px', borderRadius:14, fontSize:13, lineHeight:1.6, whiteSpace:'pre-wrap',
                background: m.role==='user' ? 'linear-gradient(135deg,#2563eb,#0ea5e9)' : 'rgba(255,255,255,0.05)',
                color: m.role==='user' ? '#fff' : 'var(--text)',
                border: m.role==='user' ? 'none' : '1px solid rgba(255,255,255,0.07)',
              }}>
                {renderText(m.content)}
              </div>
            </div>
          ))}
          {loading && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 14 }}>
              <div style={{
                height:28, width:28, borderRadius:10, flexShrink:0,
                background:'linear-gradient(135deg,#6366f1,#0ea5e9)',
                display:'flex', alignItems:'center', justifyContent:'center',
              }}>
                <Sparkles size={13} style={{ color:'#fff' }} />
              </div>
              <div style={{ display: 'flex', gap: 4 }}>
                {[0,1,2].map(i => (
                  <div key={i} style={{
                    width: 6, height: 6, borderRadius: '50%', background: '#64748b',
                    animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
                  }} />
                ))}
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        {ready ? (
          <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
            <div style={{
              display:'flex', gap:10, padding:14, borderRadius:16,
              background:'linear-gradient(135deg,rgba(99,102,241,0.1),rgba(14,165,233,0.06))',
              border:'1px solid rgba(99,102,241,0.25)',
            }}>
              <div style={{ flex:1 }}>
                <div style={{ fontSize:14, fontWeight:700, color:'var(--text)' }}>Jobby is ready to go 🎉</div>
                <div style={{ fontSize:12, color:'#94a3b8', marginTop:2 }}>
                  Your filters are set. You can still edit them in chat, or run automation now.
                </div>
                {runError && (
                  <div style={{ fontSize:12, color:'#fca5a5', marginTop:6 }}>{runError}</div>
                )}
              </div>
              <button onClick={runAutomation} disabled={startingAutomation} className="btn-primary" style={{ gap:6 }}>
                <Play size={13} /> {startingAutomation ? 'Starting…' : 'Run Automation'}
              </button>
            </div>
            <div style={{ display:'flex', flexWrap:'wrap', gap:6 }}>
              {suggestionChips.map(chip => (
                <button key={chip} onClick={() => sendSuggestion(chip)} disabled={loading} style={{
                  border:'1px solid rgba(14,165,233,.25)', background:'rgba(14,165,233,.08)',
                  color:'#7dd3fc', borderRadius:999, padding:'6px 10px', fontSize:12,
                  fontWeight:700, cursor:loading?'not-allowed':'pointer',
                }}>
                  {chip}
                </button>
              ))}
            </div>
            <div style={{ display:'flex', gap:8 }}>
              <input
                value={input} onChange={e=>setInput(e.target.value)}
                onKeyDown={e=>e.key==='Enter'&&send()}
                placeholder="Edit filters, e.g. add Europe, last 30 days, remove a role…"
                style={{ flex:1 }}
              />
              <button onClick={send} className="btn-primary" disabled={loading}><Send size={14} /></button>
            </div>
          </div>
        ) : (
          <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
            {suggestionChips.length > 0 && (
              <div style={{ display:'flex', flexWrap:'wrap', gap:6 }}>
                {suggestionChips.map(chip => (
                  <button key={chip} onClick={() => sendSuggestion(chip)} disabled={loading} style={{
                    border:'1px solid rgba(14,165,233,.25)', background:'rgba(14,165,233,.08)',
                    color:'#7dd3fc', borderRadius:999, padding:'6px 10px', fontSize:12,
                    fontWeight:700, cursor:loading?'not-allowed':'pointer',
                  }}>
                    {chip}
                  </button>
                ))}
              </div>
            )}
            <div style={{ display:'flex', gap:8 }}>
              <input
                value={input} onChange={e=>setInput(e.target.value)}
                onKeyDown={e=>e.key==='Enter'&&send()}
                placeholder={noCV ? 'Upload your CV first…' : 'Tell Jobby what you\'re looking for…'}
                disabled={noCV}
                style={{ flex:1 }}
              />
              <button onClick={send} className="btn-primary" disabled={loading || noCV}><Send size={14} /></button>
            </div>
          </div>
        )}
      </div>

      {/* ── Filter sidebar ── */}
      <FilterSidebar prefs={prefs} />
    </div>
  )
}
