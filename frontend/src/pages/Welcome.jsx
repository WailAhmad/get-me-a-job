import { useState, useEffect, useRef } from 'react'
import { connectGoogleAccount, connectAppleAccount } from '../api/client'

const SLIDES = [
  { src:'/photos/slide1.png', quote:'"I got the offer email while sitting in Business Bay. Job Land applied while I was in meetings!"', name:'Nour Al-Rashidi', role:'Marketing Manager · Dubai, UAE' },
  { src:'/photos/slide2.png', quote:'"Within 10 days I had 4 interviews lined up in Riyadh. Best decision I ever made."', name:'Khalid Al-Zahrani', role:'Business Analyst · Riyadh, KSA' },
  { src:'/photos/slide3.png', quote:'"I flew from London not knowing anyone in Dubai. Jobs Land got me hired here in 3 weeks. I\'m still pinching myself!"', name:'Emma Clarke', role:'Marketing Director · Dubai, UAE' },
  { src:'/photos/slide4.png', quote:'"Three weeks after setting up Job Land, I signed my dream contract in Abu Dhabi. Unbelievable!"',  name:'Marco Reyes',    role:'Operations Lead · Abu Dhabi, UAE' },
  { src:'/photos/slide5.png', quote:'"As a newcomer to the Gulf, I had zero connections. Jobs Land got me hired in under a month."', name:'Lara Khoury', role:'HR Specialist · Doha, Qatar' },
]

export default function Welcome({ onAuthenticated }) {
  const [slide, setSlide]     = useState(0)
  const [fade,  setFade]      = useState(true)
  const [phase, setPhase]     = useState('idle')
  const [status, setStatus]   = useState('')
  const [imported, setImported] = useState(null)
  const slideRef = useRef(null)

  useEffect(() => {
    slideRef.current = setInterval(() => {
      setFade(false)
      setTimeout(() => { setSlide(s => (s+1) % SLIDES.length); setFade(true) }, 400)
    }, 5000)
    return () => clearInterval(slideRef.current)
  }, [])

  const handleConnect = async (provider) => {
    const label = provider === 'apple' ? 'Apple' : 'Google'
    setPhase('opening')
    setStatus(`Creating a temporary ${label} development session...`)
    try {
      const result = provider === 'apple'
        ? await connectAppleAccount()
        : await connectGoogleAccount()
      setImported(result.profile)
      setPhase('done')
      setStatus(`${label} development sign-in complete.`)
      setTimeout(() => onAuthenticated?.(), 650)
    } catch (e) {
      setPhase('error')
      setStatus(e?.response?.data?.detail || e.message || `${label} sign-in failed.`)
    }
  }

  const cur = SLIDES[slide]

  return (
    <div style={{ display:'flex', minHeight:'100vh', overflow:'hidden', background:'#06080f', fontFamily:"'Inter',system-ui,sans-serif" }}>
      {/* LEFT photo panel */}
      <div style={{ flex:'0 0 60%', position:'relative', overflow:'hidden', display:'flex', flexDirection:'column' }}>
        <div style={{ position:'absolute', inset:0, backgroundImage:`url(${cur.src})`, backgroundSize:'cover', backgroundPosition:'center', opacity:fade?1:0, transition:'opacity .5s ease' }} />
        <div style={{ position:'absolute', inset:0, background:'linear-gradient(to right, #06080f 0%, transparent 60%)' }} />
        <div style={{ position:'absolute', inset:0, background:'linear-gradient(to top, #06080f 0%, transparent 50%)' }} />
        {/* logo */}
        <div style={{ position:'relative', zIndex:1, display:'flex', alignItems:'center', gap:10, padding:'28px 32px' }}>
          <img src="/jobsland_logo.png" alt="" style={{ height:36, width:36, borderRadius:10, background:'#fff', objectFit:'contain', padding:2 }} />
          <span style={{ fontSize:12, fontWeight:700, letterSpacing:'.12em', color:'rgba(255,255,255,.7)', textTransform:'uppercase' }}>Jobs Land</span>
        </div>
        {/* quote */}
        <div style={{ position:'relative', zIndex:1, marginTop:'auto', padding:'28px 32px' }}>
          <div style={{ background:'rgba(255,255,255,.06)', border:'1px solid rgba(255,255,255,.1)', borderRadius:20, padding:20, backdropFilter:'blur(16px)', opacity:fade?1:0, transition:'opacity .5s' }}>
            <p style={{ fontSize:15, fontStyle:'italic', color:'rgba(255,255,255,.9)', lineHeight:1.6, marginBottom:12 }}>{cur.quote}</p>
            <div style={{ display:'flex', alignItems:'center', gap:10 }}>
              <div style={{ height:32, width:32, borderRadius:'50%', background:'linear-gradient(135deg,#3b82f6,#0ea5e9)' }} />
              <div>
                <div style={{ fontSize:13, fontWeight:600, color:'#fff' }}>{cur.name}</div>
                <div style={{ fontSize:11, color:'rgba(255,255,255,.45)' }}>{cur.role}</div>
              </div>
            </div>
          </div>
          <div style={{ display:'flex', gap:6, marginTop:12 }}>
            {SLIDES.map((_,i) => (
              <button key={i} onClick={() => { setFade(false); setTimeout(()=>{setSlide(i);setFade(true)},300) }}
                style={{ height:5, width:i===slide?22:5, borderRadius:99, background:i===slide?'#fff':'rgba(255,255,255,.25)', border:'none', cursor:'pointer', transition:'all .3s' }} />
            ))}
          </div>
        </div>
      </div>

      {/* RIGHT auth panel */}
      <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center', padding:'32px 24px', position:'relative' }}>
        <div style={{ width:'100%', maxWidth:360 }}>

          {/* ── Medium logo, blended into dark bg ── */}
          <div style={{ display:'flex', justifyContent:'center', marginBottom:18 }}>
            <img
              src="/jobsland_logo_dark.png"
              alt="Jobs Land"
              style={{
                width:210,
                borderRadius:20,
                background:'#000',
                objectFit:'contain',
                boxShadow:'0 0 40px rgba(20,184,166,0.22), 0 0 80px rgba(14,165,233,0.1)',
              }}
            />
          </div>

          <h1 style={{ fontSize:32, fontWeight:800, lineHeight:1.15, marginBottom:8, textAlign:'center', background:'linear-gradient(135deg,#fff,#94a3b8)', WebkitBackgroundClip:'text', WebkitTextFillColor:'transparent' }}>
            Your career,<br/>on autopilot.
          </h1>
          <p style={{ fontSize:13, color:'#64748b', lineHeight:1.7, marginBottom:22, textAlign:'center' }}>
            The AI agent that discovers, scores, and applies to LinkedIn jobs — 24/7, while you focus on what matters.
          </p>

          {/* ── 3-step flow ── */}
          <div style={{ display:'flex', alignItems:'flex-start', justifyContent:'center', gap:6, marginBottom:24 }}>
            {[
              { num:'1', icon:(
                  <div style={{ display:'flex', alignItems:'center', gap:3 }}>
                    <svg height="15" width="15" viewBox="0 0 24 24">
                      <path fill="#4285F4" d="M21.6 12.23c0-.78-.07-1.53-.2-2.23H12v4.22h5.38a4.6 4.6 0 0 1-2 3.02v2.5h3.24c1.9-1.75 2.98-4.32 2.98-7.51z"/>
                      <path fill="#34A853" d="M12 22c2.7 0 4.96-.9 6.62-2.43l-3.24-2.5c-.9.6-2.05.96-3.38.96-2.6 0-4.8-1.76-5.58-4.13H3.08v2.58A10 10 0 0 0 12 22z"/>
                      <path fill="#FBBC05" d="M6.42 13.9a6 6 0 0 1 0-3.8V7.52H3.08a10 10 0 0 0 0 8.96l3.34-2.58z"/>
                      <path fill="#EA4335" d="M12 5.97c1.47 0 2.78.5 3.82 1.5l2.88-2.88C16.96 2.97 14.7 2 12 2a10 10 0 0 0-8.92 5.52l3.34 2.58C7.2 7.73 9.4 5.97 12 5.97z"/>
                    </svg>
                    <span style={{ color:'#64748b', fontSize:12 }}>or</span>
                    <svg height="16" width="16" viewBox="0 0 24 24" fill="#f8fafc" aria-hidden="true">
                      <path d="M16.37 1.51c0 1.18-.48 2.29-1.25 3.14-.8.89-2.12 1.58-3.2 1.49-.15-1.13.42-2.33 1.14-3.12.82-.9 2.22-1.58 3.31-1.51zM20.7 17.34c-.58 1.33-.86 1.93-1.6 3.11-1.04 1.62-2.5 3.64-4.31 3.66-1.6.02-2.02-1.06-4.2-1.04-2.18.01-2.64 1.07-4.24 1.05-1.81-.02-3.2-1.84-4.23-3.46C-.77 16.1-1.07 10.76.7 7.94c1.25-1.99 3.22-3.16 5.08-3.16 1.9 0 3.09 1.04 4.65 1.04 1.52 0 2.44-1.04 4.63-1.04 1.65 0 3.4.9 4.65 2.46-4.08 2.24-3.42 8.07.99 10.1z"/>
                    </svg>
                  </div>), label:'Sign in options', color:'#3b82f6' },
              { num:'2', icon:(
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14,2 14,8 20,8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/>
                  </svg>), label:'Upload CV', color:'#14b8a6' },
              { num:'3', icon:(
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#14b8a6" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                  </svg>), label:'AI Preferences', color:'#a78bfa' },
            ].map((step, i) => (
              <div key={i} style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:6, flex:1 }}>
                <div style={{ width:46, height:46, borderRadius:14, background:`${step.color}12`, border:`1px solid ${step.color}25`, display:'flex', alignItems:'center', justifyContent:'center', position:'relative' }}>
                  {step.icon}
                  <span style={{ position:'absolute', top:-6, right:-6, width:16, height:16, borderRadius:'50%', background:step.color, fontSize:9, fontWeight:800, color:'#fff', display:'flex', alignItems:'center', justifyContent:'center' }}>{step.num}</span>
                </div>
                <span style={{ fontSize:10, color:'#475569', textAlign:'center', lineHeight:1.4, fontWeight:500 }}>{step.label}</span>
              </div>
            ))}
          </div>

          <div style={{ background:'rgba(255,255,255,.04)', border:'1px solid rgba(255,255,255,.08)', borderRadius:24, padding:24, backdropFilter:'blur(24px)' }}>
            {(phase==='idle'||phase==='error') && (
              <div>
                <p style={{ fontSize:13, color:'#64748b', marginBottom:10, lineHeight:1.6 }}>Step 1: use a temporary Google or Apple development sign-in. After you enter the app, connect job-board accounts in Settings.</p>
                <p style={{ fontSize:11, color:'#38bdf8', background:'rgba(14,165,233,.08)', border:'1px solid rgba(14,165,233,.18)', borderRadius:10, padding:'8px 10px', marginBottom:12 }}>OAuth is mocked for now so product functionality can move forward. Real Google and Apple credentials can be added at the final production step.</p>
                <button id="connect-google-btn" onClick={() => handleConnect('google')} style={{ width:'100%', display:'flex', alignItems:'center', justifyContent:'center', gap:10, background:'#ffffff', color:'#1f2937', border:'1px solid rgba(255,255,255,0.16)', borderRadius:14, padding:'12px 20px', fontSize:14, fontWeight:700, cursor:'pointer', transition:'all .2s', marginBottom:10 }}
                  onMouseEnter={e=>e.currentTarget.style.background='#f8fafc'}
                  onMouseLeave={e=>e.currentTarget.style.background='#ffffff'}
                >
                  <svg height="17" width="17" viewBox="0 0 24 24">
                    <path fill="#4285F4" d="M21.6 12.23c0-.78-.07-1.53-.2-2.23H12v4.22h5.38a4.6 4.6 0 0 1-2 3.02v2.5h3.24c1.9-1.75 2.98-4.32 2.98-7.51z"/>
                    <path fill="#34A853" d="M12 22c2.7 0 4.96-.9 6.62-2.43l-3.24-2.5c-.9.6-2.05.96-3.38.96-2.6 0-4.8-1.76-5.58-4.13H3.08v2.58A10 10 0 0 0 12 22z"/>
                    <path fill="#FBBC05" d="M6.42 13.9a6 6 0 0 1 0-3.8V7.52H3.08a10 10 0 0 0 0 8.96l3.34-2.58z"/>
                    <path fill="#EA4335" d="M12 5.97c1.47 0 2.78.5 3.82 1.5l2.88-2.88C16.96 2.97 14.7 2 12 2a10 10 0 0 0-8.92 5.52l3.34 2.58C7.2 7.73 9.4 5.97 12 5.97z"/>
                  </svg>
                  Continue with Google
                  <span style={{ marginLeft:4, fontSize:11, color:'#64748b' }}>Dev</span>
                </button>
                <button id="connect-apple-btn" onClick={() => handleConnect('apple')} style={{ width:'100%', display:'flex', alignItems:'center', justifyContent:'center', gap:10, background:'#05070c', color:'#ffffff', border:'1px solid rgba(255,255,255,0.16)', borderRadius:14, padding:'12px 20px', fontSize:14, fontWeight:700, cursor:'pointer', transition:'all .2s' }}
                  onMouseEnter={e=>e.currentTarget.style.background='#111827'}
                  onMouseLeave={e=>e.currentTarget.style.background='#05070c'}
                >
                  <svg height="18" width="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                    <path d="M16.37 1.51c0 1.18-.48 2.29-1.25 3.14-.8.89-2.12 1.58-3.2 1.49-.15-1.13.42-2.33 1.14-3.12.82-.9 2.22-1.58 3.31-1.51zM20.7 17.34c-.58 1.33-.86 1.93-1.6 3.11-1.04 1.62-2.5 3.64-4.31 3.66-1.6.02-2.02-1.06-4.2-1.04-2.18.01-2.64 1.07-4.24 1.05-1.81-.02-3.2-1.84-4.23-3.46C-.77 16.1-1.07 10.76.7 7.94c1.25-1.99 3.22-3.16 5.08-3.16 1.9 0 3.09 1.04 4.65 1.04 1.52 0 2.44-1.04 4.63-1.04 1.65 0 3.4.9 4.65 2.46-4.08 2.24-3.42 8.07.99 10.1z"/>
                  </svg>
                  Continue with Apple
                  <span style={{ marginLeft:4, fontSize:11, color:'#94a3b8' }}>Dev</span>
                </button>
                {phase==='error' && <p style={{ marginTop:10, fontSize:12, color:'#f87171', background:'rgba(239,68,68,.08)', borderRadius:10, padding:'8px 12px' }}>{status}</p>}
              </div>
            )}

            {phase==='opening' && (
              <div style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:12, padding:'16px 0' }}>
                <svg style={{ height:28, width:28, animation:'spin 1s linear infinite', color:'#3b82f6' }} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle opacity=".25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                  <path opacity=".75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
                </svg>
                <p style={{ fontSize:13, color:'#64748b' }}>{status}</p>
              </div>
            )}

            {phase==='importing' && (
              <div style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:12, padding:'16px 0' }}>
                <svg style={{ height:28, width:28, animation:'spin 1s linear infinite', color:'#0ea5e9' }} viewBox="0 0 24 24" fill="none">
                  <circle opacity=".25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                  <path opacity=".75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
                </svg>
                <p style={{ fontSize:13, color:'#bae6fd' }}>{status}</p>
              </div>
            )}

            {phase==='done' && (
              <div style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:12, padding:'16px 0' }}>
                {imported?.photo
                  ? <img src={imported.photo} alt={imported.name} style={{ height:64, width:64, borderRadius:'50%', objectFit:'cover', border:'2px solid rgba(16,185,129,.4)', boxShadow:'0 0 30px rgba(16,185,129,.25)' }} />
                  : <div style={{ height:48, width:48, borderRadius:16, background:'rgba(16,185,129,.12)', border:'1px solid rgba(16,185,129,.25)', display:'flex', alignItems:'center', justifyContent:'center' }}>
                      <svg height="24" width="24" viewBox="0 0 24 24" fill="none" stroke="#34d399" strokeWidth="2.5"><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7"/></svg>
                    </div>
                }
                {imported?.name && (
                  <div style={{ textAlign:'center' }}>
                    <div style={{ fontSize:14, fontWeight:600, color:'#f1f5f9' }}>Welcome, {imported.name.split(' ')[0]}</div>
                    <div style={{ fontSize:12, color:'#64748b', marginTop:2 }}>{imported.title}</div>
                  </div>
                )}
                <p style={{ fontSize:12, color:'#34d399' }}>Entering your dashboard…</p>
              </div>
            )}
          </div>

          <p style={{ marginTop:16, textAlign:'center', fontSize:11, color:'#334155', lineHeight:1.5 }}>
            LinkedIn sync happens inside Settings after sign-in. Automation browser access is separate and only needed when running the bot.
          </p>
        </div>
      </div>
    </div>
  )
}
