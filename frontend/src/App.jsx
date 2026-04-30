import { useState, useEffect, useCallback } from 'react'
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Chat from './pages/Chat'
import CVUpload from './pages/CVUpload'
import JobExplorer from './pages/JobExplorer'
import PendingReview from './pages/PendingReview'
import AnswerMemory from './pages/AnswerMemory'
import ApplicationHistory from './pages/ApplicationHistory'
import Settings from './pages/Settings'
import Welcome from './pages/Welcome'
import { getProfileStatus, getProfile, getCV, getChat } from './api/client'

export default function App() {
  const [authenticated, setAuthenticated] = useState(null)
  const [profile, setProfile]   = useState(null)
  const [cv, setCv]             = useState(null)
  const [prefs, setPrefs]       = useState(null)
  const [bootDone, setBootDone] = useState(false)

  const refreshAll = useCallback(async () => {
    const [p, c, ch] = await Promise.allSettled([getProfile(), getCV(), getChat()])
    if (p.status === 'fulfilled') setProfile(p.value)
    if (c.status === 'fulfilled') setCv(c.value)
    if (ch.status === 'fulfilled') setPrefs(ch.value.preferences)
  }, [])

  const checkSession = useCallback(async () => {
    try {
      const s = await getProfileStatus()
      const ok = s?.connected === true
      setAuthenticated(ok)
      if (ok) {
        await refreshAll()
        setBootDone(true)
      } else {
        setBootDone(true)
      }
    } catch {
      setAuthenticated(false); setBootDone(true)
    }
  }, [refreshAll])

  useEffect(() => { checkSession() }, [checkSession])

  useEffect(() => {
    const onFocus = () => { if (authenticated !== null) refreshAll() }
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [authenticated, refreshAll])

  const onAuthenticated = async () => {
    setAuthenticated(true)
    await refreshAll()
  }

  if (!bootDone) {
    return (
      <div style={{ display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', minHeight:'100vh', gap:12, background:'#06080f' }}>
        <img src="/jobsland_logo.png" alt="Jobs Land" style={{ height:48, width:48, borderRadius:16, opacity:.85 }} />
        <svg style={{ height:20, width:20, animation:'spin 1s linear infinite', color:'#3b82f6' }} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle opacity=".25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
          <path opacity=".75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
        </svg>
      </div>
    )
  }

  if (!authenticated) {
    return <Welcome onAuthenticated={onAuthenticated} />
  }

  const logout = () => setAuthenticated(false)

  return (
    <Layout onLogout={logout} profile={profile} cv={cv} prefs={prefs}>
      <Routes>
        <Route path="/"         element={<Dashboard cv={cv} prefs={prefs} onRefresh={refreshAll} />} />
        <Route path="/chat"     element={<Chat cv={cv} onPrefsUpdate={p => setPrefs(p)} />} />
        <Route path="/cv"       element={<CVUpload onUploaded={refreshAll} />} />
        <Route path="/jobs"     element={<JobExplorer />} />
        <Route path="/pending"  element={<PendingReview onAnswered={refreshAll} />} />
        <Route path="/answers"  element={<AnswerMemory />} />
        <Route path="/history"  element={<ApplicationHistory />} />
        <Route path="/settings" element={<Settings onDisconnect={logout} />} />
        <Route path="*"         element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}
