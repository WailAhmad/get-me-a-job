import Sidebar from './Sidebar'

export default function Layout({ children, onLogout, profile, cv, prefs }) {
  return (
    <div className="app-shell" style={{ display:'flex', height:'100vh', overflow:'hidden', background:'#06080f', position:'relative' }}>
      <div style={{
        pointerEvents:'none', position:'fixed', inset:0,
        backgroundImage:'linear-gradient(rgba(147,197,253,0.03) 1px,transparent 1px),linear-gradient(90deg,rgba(147,197,253,0.03) 1px,transparent 1px)',
        backgroundSize:'48px 48px', opacity:.4,
      }} />
      <Sidebar onLogout={onLogout} profile={profile} cv={cv} prefs={prefs} />
      <main className="app-main" style={{ flex:1, minWidth:0, overflowY:'auto', position:'relative' }}>
        <div className="app-main-inner" style={{ maxWidth:1280, margin:'0 auto', padding:'28px 24px 80px' }}>
          {children}
        </div>
      </main>
    </div>
  )
}
