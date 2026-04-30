import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { sendChat, getChat, resetChat } from '../api/client'
import { Send, Bot, RefreshCw, Play } from 'lucide-react'

function renderText(text) {
  // Light markdown — bold (**…**) and line breaks
  const parts = text.split(/(\*\*[^*]+\*\*)/g)
  return parts.map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**')) return <strong key={i} style={{ color:'#f1f5f9' }}>{p.slice(2,-2)}</strong>
    return <span key={i}>{p}</span>
  })
}

export default function Chat({ cv, onPrefsUpdate }) {
  const navigate = useNavigate()
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [step, setStep] = useState('greet')
  const [prefs, setPrefs] = useState(null)
  const endRef = useRef(null)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior:'smooth' }) }, [messages])

  // Boot: load existing conversation; if empty, ask backend to greet.
  useEffect(() => {
    (async () => {
      try {
        const r = await getChat()
        if (r.history?.length) {
          setMessages(r.history.map(m => ({ role:m.role, content:m.content })))
          setStep(r.step); setPrefs(r.preferences)
          onPrefsUpdate && onPrefsUpdate(r.preferences)
        } else {
          // trigger initial greet
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

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'calc(100vh - 80px)' }}>
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:16, gap:12 }}>
        <div>
          <h1 className="page-title">AI Assistant</h1>
          <p className="page-subtitle">Set your search preferences in plain English</p>
        </div>
        <div style={{ display:'flex', gap:8 }}>
          <button onClick={reset} disabled={loading} style={{ display:'flex', alignItems:'center', gap:6, padding:'8px 12px', borderRadius:10, border:'1px solid rgba(255,255,255,0.08)', background:'rgba(255,255,255,0.03)', color:'#94a3b8', fontSize:12, cursor:'pointer' }}>
            <RefreshCw size={12} /> Reset
          </button>
        </div>
      </div>

      {noCV && (
        <div className="card" style={{ marginBottom:14, background:'rgba(245,158,11,0.06)', border:'1px solid rgba(245,158,11,0.22)' }}>
          <div style={{ fontSize:13, color:'#fbbf24', marginBottom:6, fontWeight:600 }}>Upload your CV first</div>
          <div style={{ fontSize:12, color:'#94a3b8', marginBottom:10 }}>I match jobs to your real skills — I need your CV before we set preferences.</div>
          <button onClick={() => navigate('/cv')} className="btn-primary" style={{ gap:6 }}>Go to My CV →</button>
        </div>
      )}

      {/* Preference summary chips */}
      {prefs && (prefs.country || prefs.recency_days || prefs.roles?.length) && (
        <div style={{ display:'flex', gap:6, flexWrap:'wrap', marginBottom:10 }}>
          {prefs.country && <span className="badge badge-blue">📍 {prefs.country}</span>}
          {prefs.recency_days && <span className="badge badge-blue">🗓 last {prefs.recency_days}d</span>}
          {prefs.roles?.slice(0,3).map(r => <span key={r} className="badge badge-blue">🎯 {r}</span>)}
          {prefs.roles?.length > 3 && <span className="badge badge-blue">+{prefs.roles.length-3} more</span>}
        </div>
      )}

      <div className="card" style={{ flex:1, overflowY:'auto', marginBottom:12, padding:16 }}>
        {messages.map((m,i) => (
          <div key={i} style={{ display:'flex', gap:10, marginBottom:14, justifyContent:m.role==='user'?'flex-end':'flex-start' }}>
            {m.role==='assistant' && <div style={{ height:28, width:28, borderRadius:'50%', background:'linear-gradient(135deg,#2563eb,#0ea5e9)', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0 }}><Bot size={14} style={{ color:'#fff' }} /></div>}
            <div style={{ maxWidth:'78%', padding:'10px 14px', borderRadius:14, fontSize:13, lineHeight:1.6, background:m.role==='user'?'linear-gradient(135deg,#2563eb,#0ea5e9)':'rgba(255,255,255,0.05)', color:m.role==='user'?'#fff':'#cbd5e1', border:m.role==='user'?'none':'1px solid rgba(255,255,255,0.07)', whiteSpace:'pre-wrap' }}>
              {renderText(m.content)}
            </div>
          </div>
        ))}
        {loading && <div style={{ fontSize:12, color:'#475569', textAlign:'center' }}>Thinking…</div>}
        <div ref={endRef} />
      </div>

      {ready ? (
        <div style={{ display:'flex', gap:10, padding:14, borderRadius:16, background:'linear-gradient(135deg,rgba(167,139,250,0.1),rgba(56,189,248,0.06))', border:'1px solid rgba(167,139,250,0.25)' }}>
          <div style={{ flex:1 }}>
            <div style={{ fontSize:13, fontWeight:600, color:'#f1f5f9' }}>You're ready to go 🎉</div>
            <div style={{ fontSize:12, color:'#94a3b8', marginTop:2 }}>Run automation now and I'll start applying.</div>
          </div>
          <button onClick={() => navigate('/')} className="btn-primary" style={{ gap:6 }}>
            <Play size={13} /> Run Automation
          </button>
        </div>
      ) : (
        <div style={{ display:'flex', gap:8 }}>
          <input value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>e.key==='Enter'&&send()} placeholder={noCV ? 'Upload your CV first…' : 'Type your answer…'} disabled={noCV} style={{ flex:1 }} />
          <button onClick={send} className="btn-primary" disabled={loading || noCV}><Send size={14} /></button>
        </div>
      )}
    </div>
  )
}
