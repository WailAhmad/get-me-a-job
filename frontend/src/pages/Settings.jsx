import { useState, useEffect } from 'react'
import {
  getLinkedInSessionStatus,
  verifyLinkedInSession,
  clearLinkedInSession,
  openLinkedInLogin,
  confirmLinkedInLogin,
  checkLoginStatus,
  importProfile,
  getProfile,
  getJobSources,
  connectJobSource,
  disconnectJobSource,
  getLiveMode,
  setLiveMode,
  linkedinDiagnose,
  testLinkedinSearch,
  getAllSettings,
  updateSetting,
} from '../api/client'
import { Link2, RefreshCw, LogOut, UserRound, Globe2, CheckCircle2, PlugZap, Zap, Activity, Briefcase, Save } from 'lucide-react'

const EDUCATION_OPTIONS = ['PhD', "Master's", "Bachelor's", 'Diploma', 'High School']
const NOTICE_OPTIONS    = ['Immediate', '2 weeks', '1 month', '2 months', '3 months', '6 months']

export default function Settings({ onDisconnect }) {
  const [session, setSession]   = useState(null)
  const [loginMsg, setLoginMsg] = useState('')
  const [profile, setProfile] = useState(null)
  const [loading, setLoading]   = useState(true)
  const [connecting, setConnecting] = useState(false)
  const [sources, setSources] = useState([])
  const [sourceMsg, setSourceMsg] = useState('')
  const [liveMode, setLiveModeState] = useState({ live_mode: false, linkedin_session: false, effective: false })
  const [liveMsg, setLiveMsg] = useState('')
  const [liveBusy, setLiveBusy] = useState(false)
  const [diagBusy, setDiagBusy] = useState(false)
  const [diagResult, setDiagResult] = useState(null)

  // Job preferences
  const [prefs, setPrefs] = useState({
    salary_expectation: '', current_salary: '', notice_period: '',
    education_level: '', work_authorization: 'yes', visa_sponsorship: 'no',
    willing_to_relocate: 'yes', daily_cap: '50',
  })
  const [prefsBusy, setPrefsBusy] = useState(false)
  const [prefsMsg, setPrefsMsg] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const [s, p, src, lm, allSettings] = await Promise.all([
        getLinkedInSessionStatus(), getProfile(), getJobSources(), getLiveMode(),
        getAllSettings().catch(() => null),
      ])
      setSession(s)
      setProfile(p)
      setSources(src.sources || [])
      setLiveModeState(lm)
      if (allSettings) {
        setPrefs(prev => ({
          ...prev,
          salary_expectation: allSettings.salary_expectation ?? '',
          current_salary:     allSettings.current_salary ?? '',
          notice_period:      allSettings.notice_period ?? '',
          education_level:    allSettings.education_level ?? '',
          work_authorization: allSettings.work_authorization ?? 'yes',
          visa_sponsorship:   allSettings.visa_sponsorship ?? 'no',
          willing_to_relocate:allSettings.willing_to_relocate ?? 'yes',
          daily_cap:          String(allSettings.daily_cap ?? '50'),
        }))
      }
    } catch {}
    setLoading(false)
  }

  const savePrefs = async () => {
    setPrefsBusy(true); setPrefsMsg('')
    try {
      await Promise.all(
        Object.entries(prefs).map(([k, v]) => updateSetting(k, v))
      )
      setPrefsMsg('Preferences saved ✓')
      setTimeout(() => setPrefsMsg(''), 3000)
    } catch (e) {
      setPrefsMsg(e.response?.data?.detail || e.message || 'Save failed')
    } finally { setPrefsBusy(false) }
  }

  const toggleLive = async () => {
    setLiveBusy(true); setLiveMsg('')
    try {
      const r = await setLiveMode(!liveMode.live_mode)
      setLiveMsg(r.message || '')
      const lm = await getLiveMode()
      setLiveModeState(lm)
    } catch (e) {
      setLiveMsg(e.response?.data?.detail || e.message)
    } finally { setLiveBusy(false) }
  }

  const runDiag = async () => {
    setDiagBusy(true); setDiagResult(null)
    try {
      const diag = await linkedinDiagnose()
      // Try a tiny real search to confirm the session truly works
      let search = null
      try {
        search = await testLinkedinSearch({ keywords:'AI Product Manager', country:'UAE', recency_days:7, max_results:3, headless:true })
      } catch (e) {
        search = { error: e.response?.data?.detail || e.message }
      }
      setDiagResult({ diag, search })
    } catch (e) {
      setDiagResult({ error: e.response?.data?.detail || e.message })
    } finally { setDiagBusy(false) }
  }
  useEffect(() => { load() }, [])

  const verify = async () => {
    setLoginMsg('Verifying…')
    try { const r = await verifyLinkedInSession(); setLoginMsg(r.message) } catch (e) { setLoginMsg(e.message) }
  }

  const connect = async () => {
    setConnecting(true)
    setLoginMsg('Opening LinkedIn sign-in window...')
    try {
      const r = await openLinkedInLogin()
      setLoginMsg(r.message || 'LinkedIn window opened. Complete sign-in there, then return here.')
      const deadline = Date.now() + 120000
      const poll = async () => {
        if (Date.now() > deadline) {
          setConnecting(false)
          setLoginMsg('Still waiting for LinkedIn login. After signing in, click Confirm manually.')
          return
        }
        try {
          const status = await checkLoginStatus()
          if (status.logged_in) {
            await importProfile().catch(() => {})
            await connectJobSource('linkedin').catch(() => {})
            await load()
            setConnecting(false)
            setLoginMsg('LinkedIn connected and profile imported.')
            return
          }
        } catch {}
        setTimeout(poll, 2000)
      }
      poll()
    } catch (e) {
      setConnecting(false)
      setLoginMsg(e.message)
    }
  }

  const confirm = async () => {
    setLoginMsg('Confirming LinkedIn session...')
    try {
      const r = await confirmLinkedInLogin()
      if (r.success) {
        await importProfile().catch(() => {})
        await connectJobSource('linkedin').catch(() => {})
        await load()
      }
      setConnecting(false)
      setLoginMsg(r.message)
    } catch (e) {
      setLoginMsg(e.message)
    }
  }

  const syncLinkedInProfile = async () => {
    setLoginMsg('Syncing LinkedIn profile...')
    try {
      const r = await importProfile()
      setProfile(r.profile)
      setLoginMsg('LinkedIn profile details synced.')
    } catch (e) {
      setLoginMsg(e.message)
    }
  }

  const disconnect = async () => {
    if (!confirm('Log out of Job Land? You will be taken back to the login screen.')) return
    await clearLinkedInSession().catch(()=>{})
    if (onDisconnect) onDisconnect()
  }

  const toggleSource = async (source) => {
    setSourceMsg('')
    try {
      if (source.connected) {
        await disconnectJobSource(source.id)
        setSourceMsg(`${source.name} disconnected from discovery.`)
      } else {
        await connectJobSource(source.id)
        setSourceMsg(`${source.name} added to discovery. Site-specific apply automation will use this connection when enabled.`)
      }
      await load()
    } catch (e) {
      setSourceMsg(e.message)
    }
  }

  return (
    <div className="animate-fade-in" style={{ maxWidth:860 }}>
      <h1 className="page-title">Settings</h1>
      <p className="page-subtitle" style={{ marginBottom:24 }}>Manage sign-in, profile sync, and connected job sources</p>

      {loading ? <div style={{ display:'flex', justifyContent:'center', padding:40 }}><RefreshCw size={18} style={{ color:'#3b82f6', animation:'spin 1s linear infinite' }} /></div> : (
        <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
        <div className="card" style={{ display:'flex', flexDirection:'column', gap:14 }}>
          <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:4 }}>
            <UserRound size={16} style={{ color:'#60a5fa' }} />
            <span style={{ fontSize:14, fontWeight:600, color:'#f1f5f9' }}>Account Profile</span>
          </div>

          <div style={{ display:'flex', alignItems:'center', gap:12, background:'rgba(255,255,255,.04)', border:'1px solid rgba(255,255,255,.07)', borderRadius:12, padding:'12px 14px' }}>
            {profile?.photo ? (
              <img src={profile.photo} alt={profile.name} style={{ height:38, width:38, borderRadius:'50%', objectFit:'cover' }} />
            ) : (
              <div style={{ height:38, width:38, borderRadius:'50%', background:'linear-gradient(135deg,#2563eb,#0ea5e9)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:14, fontWeight:800 }}>
                {(profile?.name || 'W').slice(0,1)}
              </div>
            )}
            <div style={{ flex:1, minWidth:0 }}>
              <div style={{ fontSize:13, fontWeight:700, color:'#e2e8f0', whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{profile?.name || 'Google account connected'}</div>
              <div style={{ fontSize:11, color:'#64748b', whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{profile?.title || 'Sync LinkedIn to import title'}</div>
            </div>
            <button onClick={syncLinkedInProfile} className="btn-secondary" style={{ padding:'8px 12px' }}>
              Sync LinkedIn Profile
            </button>
          </div>
        </div>

        {/* ─── Job Application Preferences ─── */}
        <div className="card" style={{ display:'flex', flexDirection:'column', gap:16 }}>
          <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:4 }}>
            <Briefcase size={16} style={{ color:'#a78bfa' }} />
            <span style={{ fontSize:14, fontWeight:600, color:'#f1f5f9' }}>Job Application Preferences</span>
          </div>
          <p style={{ fontSize:12, color:'#64748b', lineHeight:1.5, marginTop:-8 }}>
            These answers fill form fields automatically. Set them once — the AI will use them on every application instead of guessing.
          </p>

          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(230px,1fr))', gap:12 }}>
            {/* Expected salary */}
            <label style={{ display:'flex', flexDirection:'column', gap:5 }}>
              <span style={{ fontSize:11, fontWeight:600, color:'#94a3b8', textTransform:'uppercase', letterSpacing:'.05em' }}>Expected Salary</span>
              <input
                value={prefs.salary_expectation}
                onChange={e => setPrefs(p => ({ ...p, salary_expectation: e.target.value }))}
                placeholder="e.g. 25000 (monthly) or 300000 (annual)"
                style={{ width:'100%' }}
              />
            </label>

            {/* Current salary */}
            <label style={{ display:'flex', flexDirection:'column', gap:5 }}>
              <span style={{ fontSize:11, fontWeight:600, color:'#94a3b8', textTransform:'uppercase', letterSpacing:'.05em' }}>Current Salary <span style={{ fontWeight:400, textTransform:'none', letterSpacing:0 }}>(optional)</span></span>
              <input
                value={prefs.current_salary}
                onChange={e => setPrefs(p => ({ ...p, current_salary: e.target.value }))}
                placeholder="e.g. 22000"
                style={{ width:'100%' }}
              />
            </label>

            {/* Notice period */}
            <label style={{ display:'flex', flexDirection:'column', gap:5 }}>
              <span style={{ fontSize:11, fontWeight:600, color:'#94a3b8', textTransform:'uppercase', letterSpacing:'.05em' }}>Notice Period</span>
              <select
                value={prefs.notice_period}
                onChange={e => setPrefs(p => ({ ...p, notice_period: e.target.value }))}
                style={{ width:'100%' }}
              >
                <option value="">— select —</option>
                {NOTICE_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            </label>

            {/* Education */}
            <label style={{ display:'flex', flexDirection:'column', gap:5 }}>
              <span style={{ fontSize:11, fontWeight:600, color:'#94a3b8', textTransform:'uppercase', letterSpacing:'.05em' }}>Highest Education</span>
              <select
                value={prefs.education_level}
                onChange={e => setPrefs(p => ({ ...p, education_level: e.target.value }))}
                style={{ width:'100%' }}
              >
                <option value="">— select —</option>
                {EDUCATION_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            </label>

            {/* Visa sponsorship */}
            <label style={{ display:'flex', flexDirection:'column', gap:5 }}>
              <span style={{ fontSize:11, fontWeight:600, color:'#94a3b8', textTransform:'uppercase', letterSpacing:'.05em' }}>Requires Visa Sponsorship?</span>
              <select
                value={prefs.visa_sponsorship}
                onChange={e => setPrefs(p => ({ ...p, visa_sponsorship: e.target.value }))}
                style={{ width:'100%' }}
              >
                <option value="no">No</option>
                <option value="yes">Yes</option>
              </select>
            </label>

            {/* Relocation */}
            <label style={{ display:'flex', flexDirection:'column', gap:5 }}>
              <span style={{ fontSize:11, fontWeight:600, color:'#94a3b8', textTransform:'uppercase', letterSpacing:'.05em' }}>Willing to Relocate?</span>
              <select
                value={prefs.willing_to_relocate}
                onChange={e => setPrefs(p => ({ ...p, willing_to_relocate: e.target.value }))}
                style={{ width:'100%' }}
              >
                <option value="yes">Yes</option>
                <option value="no">No</option>
              </select>
            </label>

            {/* Daily cap */}
            <label style={{ display:'flex', flexDirection:'column', gap:5 }}>
              <span style={{ fontSize:11, fontWeight:600, color:'#94a3b8', textTransform:'uppercase', letterSpacing:'.05em' }}>Daily Apply Cap <span style={{ fontWeight:400, textTransform:'none', letterSpacing:0 }}>(max 50 recommended)</span></span>
              <input
                type="number"
                min="1" max="100"
                value={prefs.daily_cap}
                onChange={e => setPrefs(p => ({ ...p, daily_cap: e.target.value }))}
                style={{ width:'100%' }}
              />
            </label>
          </div>

          {prefsMsg && (
            <div style={{ fontSize:12, color: prefsMsg.includes('✓') ? '#34d399' : '#f87171',
              background: prefsMsg.includes('✓') ? 'rgba(52,211,153,0.08)' : 'rgba(248,113,113,0.08)',
              border: `1px solid ${prefsMsg.includes('✓') ? 'rgba(52,211,153,0.22)' : 'rgba(248,113,113,0.22)'}`,
              borderRadius:10, padding:'8px 12px' }}>
              {prefsMsg}
            </div>
          )}

          <button onClick={savePrefs} disabled={prefsBusy} className="btn-primary" style={{ gap:6, width:'fit-content' }}>
            <Save size={13} /> {prefsBusy ? 'Saving…' : 'Save Preferences'}
          </button>
        </div>

        <div className="card" style={{ display:'flex', flexDirection:'column', gap:14, border:`1px solid ${liveMode.effective?'rgba(16,185,129,0.30)':'rgba(245,158,11,0.25)'}`, background:liveMode.effective?'linear-gradient(135deg,rgba(16,185,129,0.08),rgba(56,189,248,0.04))':'linear-gradient(135deg,rgba(245,158,11,0.06),rgba(56,189,248,0.03))' }}>
          <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:4 }}>
            <Zap size={16} style={{ color: liveMode.effective ? '#34d399' : '#fbbf24' }} />
            <span style={{ fontSize:14, fontWeight:700, color:'#f1f5f9' }}>Live Mode</span>
            <span className={`badge ${liveMode.effective?'badge-green':'badge-amber'}`} style={{ marginLeft:'auto' }}>
              {liveMode.effective ? 'LIVE — real submissions' : 'REAL MODE OFF'}
            </span>
          </div>
          <p style={{ fontSize:12, color:'#94a3b8', lineHeight:1.55 }}>
            The automation engine drives a real Selenium browser using your saved LinkedIn session
            to search jobs and submit Easy Apply forms. When real mode is off or LinkedIn is not connected,
            automation will not run and no simulated jobs or applications are generated.
          </p>

          {!liveMode.linkedin_session && (
            <div style={{ fontSize:12, color:'#fbbf24', background:'rgba(245,158,11,.08)', border:'1px solid rgba(245,158,11,.2)', borderRadius:10, padding:'8px 12px' }}>
              ⚠ Connect LinkedIn below before turning on live mode.
            </div>
          )}

          {liveMsg && <div style={{ fontSize:12, color:'#93c5fd', background:'rgba(59,130,246,.08)', border:'1px solid rgba(59,130,246,.2)', borderRadius:10, padding:'8px 12px' }}>{liveMsg}</div>}

          <div style={{ display:'flex', gap:8, flexWrap:'wrap', alignItems:'center' }}>
            <button onClick={toggleLive} disabled={liveBusy || (!liveMode.linkedin_session && !liveMode.live_mode)} className={liveMode.live_mode?'btn-secondary':'btn-primary'} style={{ gap:6 }}>
              <Zap size={13} /> {liveBusy ? 'Saving…' : (liveMode.live_mode ? 'Turn OFF live mode' : 'Turn ON live mode')}
            </button>
            <button onClick={runDiag} disabled={diagBusy || !liveMode.linkedin_session} className="btn-secondary" style={{ gap:6 }}>
              <Activity size={13} /> {diagBusy ? 'Running…' : 'Run live diagnostic'}
            </button>
          </div>

          {diagResult && (
            <pre style={{ fontSize:11, color:'#cbd5e1', background:'rgba(0,0,0,.35)', border:'1px solid rgba(255,255,255,.06)', borderRadius:10, padding:12, overflow:'auto', maxHeight:280 }}>
{JSON.stringify(diagResult, null, 2)}
            </pre>
          )}
        </div>

        <div className="card" style={{ display:'flex', flexDirection:'column', gap:14 }}>
          <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:4 }}>
            <Link2 size={16} style={{ color:'#0077b5' }} />
            <span style={{ fontSize:14, fontWeight:600, color:'#f1f5f9' }}>LinkedIn Automation Session</span>
          </div>

          <div style={{ display:'flex', alignItems:'center', gap:10, background:'rgba(255,255,255,.04)', border:'1px solid rgba(255,255,255,.07)', borderRadius:12, padding:'12px 14px' }}>
            <div style={{ height:8, width:8, borderRadius:'50%', background:session?.has_session?'#10b981':'#f59e0b', flexShrink:0 }} />
            <span style={{ flex:1, fontSize:13, color:'#cbd5e1' }}>{session?.has_session ? 'Connected — LinkedIn session is active' : 'Not connected — use the connect button below'}</span>
            {session?.has_session && <button onClick={verify} style={{ fontSize:11, color:'#64748b', background:'none', border:'none', cursor:'pointer' }}>Verify</button>}
          </div>

          {loginMsg && <div style={{ fontSize:12, color:'#93c5fd', background:'rgba(59,130,246,.08)', border:'1px solid rgba(59,130,246,.2)', borderRadius:10, padding:'8px 12px' }}>{loginMsg}</div>}

          <div style={{ display:'flex', gap:8, flexWrap:'wrap' }}>
            <button onClick={connect} disabled={connecting} className="btn-primary">
              {session?.has_session ? 'Reconnect LinkedIn' : 'Connect LinkedIn'}
            </button>
            {connecting && (
              <button onClick={confirm} className="btn-secondary">
                Confirm manually
              </button>
            )}
          </div>

          {session?.has_session && (
            <button onClick={disconnect} style={{ display:'flex', alignItems:'center', gap:6, padding:'9px 16px', borderRadius:12, border:'1px solid rgba(255,255,255,.08)', background:'rgba(255,255,255,.04)', color:'#94a3b8', fontSize:13, fontWeight:500, cursor:'pointer', width:'fit-content' }}>
              <LogOut size={13} /> Log out of JobsLand
            </button>
          )}

          <p style={{ fontSize:11, color:'#334155' }}>🔒 Your LinkedIn password is <strong style={{ color:'#475569' }}>never stored</strong>. Only the browser session cookie is saved locally.</p>
        </div>

        <div className="card" style={{ display:'flex', flexDirection:'column', gap:16 }}>
          <div style={{ display:'flex', alignItems:'flex-start', justifyContent:'space-between', gap:12 }}>
            <div>
              <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:4 }}>
                <Globe2 size={16} style={{ color:'#38bdf8' }} />
                <span style={{ fontSize:14, fontWeight:700, color:'#f1f5f9' }}>Job Sources</span>
              </div>
              <p style={{ fontSize:12, color:'#64748b', lineHeight:1.5 }}>
                Connect the boards the agent should search. LinkedIn is required for profile sync and LinkedIn Easy Apply. Other boards stay unavailable until their real site-specific flows are implemented.
              </p>
            </div>
            <span className="badge badge-blue" style={{ whiteSpace:'nowrap' }}>
              {sources.filter(s => s.connected).length} connected
            </span>
          </div>

          {sourceMsg && (
            <div style={{ fontSize:12, color:'#93c5fd', background:'rgba(59,130,246,.08)', border:'1px solid rgba(59,130,246,.2)', borderRadius:10, padding:'8px 12px' }}>
              {sourceMsg}
            </div>
          )}

          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(260px, 1fr))', gap:10 }}>
            {sources.map(source => (
              <div key={source.id} style={{ background:'rgba(255,255,255,.035)', border:`1px solid ${source.connected ? 'rgba(52,211,153,.24)' : 'rgba(255,255,255,.075)'}`, borderRadius:16, padding:14, display:'flex', flexDirection:'column', gap:12 }}>
                <div style={{ display:'flex', alignItems:'flex-start', gap:10 }}>
                  <div style={{ height:36, width:36, borderRadius:12, background:source.connected?'rgba(16,185,129,.12)':'rgba(59,130,246,.10)', border:`1px solid ${source.connected ? 'rgba(52,211,153,.22)' : 'rgba(96,165,250,.18)'}`, display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0 }}>
                    {source.connected ? <CheckCircle2 size={17} style={{ color:'#34d399' }} /> : <PlugZap size={17} style={{ color:'#60a5fa' }} />}
                  </div>
                  <div style={{ minWidth:0, flex:1 }}>
                    <div style={{ display:'flex', alignItems:'center', gap:8, flexWrap:'wrap' }}>
                      <span style={{ fontSize:13, fontWeight:700, color:'#e2e8f0' }}>{source.name}</span>
                      <span className={`badge ${source.connected ? 'badge-green' : 'badge-gray'}`}>{source.connected ? 'Connected' : 'Not connected'}</span>
                    </div>
                    <div style={{ fontSize:11, color:'#64748b', marginTop:2 }}>{source.region}</div>
                  </div>
                </div>

                <p style={{ fontSize:11, color:'#7c8aa0', lineHeight:1.5, minHeight:34 }}>{source.notes}</p>

                <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
                  {(source.capabilities || []).map(cap => (
                    <span key={cap} className="badge badge-blue" style={{ fontSize:10, padding:'2px 8px' }}>{cap}</span>
                  ))}
                </div>

                <div style={{ display:'flex', gap:8, marginTop:'auto' }}>
                  {source.id === 'linkedin' ? (
                    <button onClick={connect} disabled={connecting} className={source.connected ? 'btn-secondary' : 'btn-primary'} style={{ padding:'8px 12px', width:'100%', justifyContent:'center' }}>
                      {source.connected ? 'Reconnect LinkedIn' : 'Connect LinkedIn'}
                    </button>
                  ) : (
                    <button onClick={() => toggleSource(source)} className={source.connected ? 'btn-secondary' : 'btn-primary'} style={{ padding:'8px 12px', width:'100%', justifyContent:'center' }}>
                      {source.connected ? 'Disconnect' : 'Connect'}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
        </div>
      )}
    </div>
  )
}
