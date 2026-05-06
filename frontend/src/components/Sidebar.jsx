import { NavLink } from 'react-router-dom'
import { LayoutDashboard, MessageSquare, FileText, Search, Clock, BookOpen, History, Settings, LogOut, Sun, Moon } from 'lucide-react'
import { clearLinkedInSession } from '../api/client'
import { useTheme } from '../ThemeContext'
import Logo from './Logo'

const nav = [
  { to:'/',         icon:LayoutDashboard, label:'Dashboard'   },
  { to:'/chat',     icon:MessageSquare,   label:'Jobby'},
  { to:'/cv',       icon:FileText,        label:'My CV'       },
  { to:'/jobs',     icon:Search,          label:'Job Explorer'},
  { to:'/pending',  icon:Clock,           label:'Pending'     },
  { to:'/answers',  icon:BookOpen,        label:'Answers'     },
  { to:'/history',  icon:History,         label:'History'     },
  { to:'/settings', icon:Settings,        label:'Settings'    },
]

const S = {
  aside: {
    width:240, flexShrink:0, height:'100vh', display:'flex', flexDirection:'column',
    background:'var(--bg-sidebar)', borderRight:'1px solid var(--border)',
    position:'relative', zIndex:10,
  },
  logo: {
    padding:'20px 16px', borderBottom:'1px solid var(--border)',
    display:'flex', alignItems:'center', gap:14,
  },
  nav:  { flex:1, overflowY:'auto', padding:'12px 8px' },
  link: { display:'flex', alignItems:'center', gap:10, padding:'9px 12px', borderRadius:12, fontSize:13, fontWeight:500, textDecoration:'none', color:'var(--nav-text)', transition:'all .15s', marginBottom:2 },
  linkActive: { color:'var(--nav-active-text)', background:'var(--nav-active-bg)', border:'1px solid var(--nav-active-border)', fontWeight:600 },
  footer: { padding:'12px', borderTop:'1px solid var(--border)' },
  card:   { background:'var(--bg-card)', border:'1px solid var(--border)', borderRadius:16, padding:12 },
}

export default function Sidebar({ onLogout, profile, cv, prefs }) {
  const { theme, toggle } = useTheme()

  const handleLogout = async () => {
    try { await clearLinkedInSession() } catch {}
    if (onLogout) onLogout()
  }

  const name  = cv?.name || profile?.name || 'Candidate'
  const title = cv?.seniority ? `${cv.seniority} profile` : (profile?.title || 'Ready to search')
  const photo = profile?.photo
  const initial = name.slice(0,1).toUpperCase()

  const status = !cv?.uploaded ? { text:'Upload CV', color:'#f59e0b' }
               : !prefs?.ready ? { text:'Set prefs', color:'#38bdf8' }
               :                  { text:'Active',    color:'#34d399' }

  return (
    <aside className="sidebar" style={S.aside}>
      <div className="sidebar-logo" style={S.logo}>
        <Logo height={58} width={54} style={{ borderRadius:16 }} />
        <div style={{ flex:1, minWidth:0, display:'flex', flexDirection:'column', justifyContent:'center' }}>
          <div style={{ fontSize:14, lineHeight:1.28, color:'var(--text-muted)', fontWeight:600, letterSpacing:0 }}>
            Career search,<br />
            guided by AI
          </div>
        </div>
      </div>

      <nav className="sidebar-nav" style={S.nav}>
        {nav.map(({ to, icon:Icon, label }) => (
          <NavLink key={to} to={to} end={to==='/'} style={({ isActive }) => ({ ...S.link, ...(isActive ? S.linkActive : {}) })}>
            <Icon size={15} style={{ flexShrink:0 }} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-footer" style={S.footer}>
        {/* Theme toggle */}
        <button onClick={toggle} style={{
          display:'flex', alignItems:'center', justifyContent:'space-between', gap:8,
          width:'100%', padding:'8px 10px', marginBottom:8, borderRadius:10,
          border:'1px solid var(--border)', background:'var(--bg-card)',
          color:'var(--text-muted)', fontSize:12, fontWeight:500,
          cursor:'pointer', transition:'all .15s',
        }}
          onMouseEnter={e => { e.currentTarget.style.color='var(--text)'; e.currentTarget.style.background='var(--bg-hover)' }}
          onMouseLeave={e => { e.currentTarget.style.color=''; e.currentTarget.style.background='' }}
        >
          <span style={{ display:'flex', alignItems:'center', gap:6 }}>
            {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
            Appearance
          </span>
          <span style={{ fontSize:11, fontWeight:700, color:'var(--text-secondary)' }}>
            {theme === 'dark' ? 'Dark' : 'Light'}
          </span>
        </button>

        <div style={S.card}>
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:8 }}>
            <span style={{ fontSize:11, color:'var(--text-dim)', fontWeight:600 }}>PROFILE</span>
            <span style={{ fontSize:10, fontWeight:600, padding:'2px 8px', borderRadius:99, background:`${status.color}14`, color:status.color, border:`1px solid ${status.color}33` }}>{status.text}</span>
          </div>
          <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:10 }}>
            {photo ? (
              <img src={photo} alt={name} style={{ height:32, width:32, borderRadius:'50%', objectFit:'cover', flexShrink:0, border:'1px solid var(--border)' }} />
            ) : (
              <div style={{ height:32, width:32, borderRadius:'50%', background:'linear-gradient(135deg,#1d4ed8,#0ea5e9)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:13, fontWeight:700, color:'#fff', flexShrink:0 }}>{initial}</div>
            )}
            <div style={{ overflow:'hidden' }}>
              <div style={{ fontSize:12, fontWeight:600, color:'var(--text-secondary)', whiteSpace:'nowrap', textOverflow:'ellipsis', overflow:'hidden' }}>{name}</div>
              <div style={{ fontSize:11, color:'var(--text-dim)', whiteSpace:'nowrap', textOverflow:'ellipsis', overflow:'hidden' }}>{title}</div>
            </div>
          </div>
          <button onClick={handleLogout} id="logout-btn" style={{ display:'flex', alignItems:'center', gap:6, width:'100%', padding:'7px 10px', borderRadius:10, border:'1px solid var(--border)', background:'var(--bg-subtle)', color:'var(--text-muted)', fontSize:12, fontWeight:500, cursor:'pointer', transition:'all .15s' }}
            onMouseEnter={e => { e.currentTarget.style.color='var(--text-secondary)'; e.currentTarget.style.borderColor='var(--border-strong)'; e.currentTarget.style.background='var(--bg-hover)' }}
            onMouseLeave={e => { e.currentTarget.style.color=''; e.currentTarget.style.borderColor=''; e.currentTarget.style.background='' }}
          >
            <LogOut size={12} /> Log out of JobsLand
          </button>
        </div>
      </div>
    </aside>
  )
}
