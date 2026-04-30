import { NavLink } from 'react-router-dom'
import { LayoutDashboard, MessageSquare, FileText, Search, Clock, BookOpen, History, Settings, LogOut } from 'lucide-react'
import { clearLinkedInSession } from '../api/client'

const nav = [
  { to:'/',         icon:LayoutDashboard, label:'Dashboard'   },
  { to:'/chat',     icon:MessageSquare,   label:'AI Assistant'},
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
    background:'linear-gradient(180deg,rgba(9,19,36,0.96) 0%,rgba(7,11,20,0.94) 100%)',
    borderRight:'1px solid rgba(255,255,255,0.07)', position:'relative', zIndex:10,
  },
  logo: {
    padding:'20px 16px', borderBottom:'1px solid rgba(255,255,255,0.07)',
    display:'flex', alignItems:'center', gap:10,
  },
  nav:  { flex:1, overflowY:'auto', padding:'12px 8px' },
  link: { display:'flex', alignItems:'center', gap:10, padding:'9px 12px', borderRadius:12, fontSize:13, fontWeight:500, textDecoration:'none', color:'#64748b', transition:'all .15s', marginBottom:2 },
  linkActive: { color:'#f1f5f9', background:'linear-gradient(135deg,rgba(37,99,235,.22),rgba(14,165,233,.12))', border:'1px solid rgba(125,211,252,.22)', fontWeight:600 },
  footer: { padding:'12px', borderTop:'1px solid rgba(255,255,255,0.07)' },
  card:   { background:'rgba(255,255,255,0.04)', border:'1px solid rgba(255,255,255,0.07)', borderRadius:16, padding:12 },
}

export default function Sidebar({ onLogout, profile, cv, prefs }) {
  const handleLogout = async () => {
    try { await clearLinkedInSession() } catch {}
    if (onLogout) onLogout()
  }

  const name  = profile?.name  || 'You'
  const title = profile?.title || 'Welcome'
  const photo = profile?.photo
  const initial = name.slice(0,1).toUpperCase()

  const status = !cv?.uploaded ? { text:'Upload CV', color:'#f59e0b' }
               : !prefs?.ready ? { text:'Set prefs', color:'#38bdf8' }
               :                  { text:'Active',    color:'#34d399' }

  return (
    <aside className="sidebar" style={S.aside}>
      <div className="sidebar-logo" style={S.logo}>
        <img src="/jobsland_logo.png" alt="Jobs Land" style={{ height:36, width:36, borderRadius:10, flexShrink:0, background:'#fff', objectFit:'contain', padding:2 }} />
        <div>
          <div style={{ fontSize:13, fontWeight:700, color:'#f1f5f9', letterSpacing:'.01em' }}>Jobs Land</div>
          <div style={{ fontSize:11, color:'#475569' }}>Your dream job, guided by AI</div>
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
        <div style={S.card}>
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:8 }}>
            <span style={{ fontSize:11, color:'#475569', fontWeight:600 }}>PROFILE</span>
            <span style={{ fontSize:10, fontWeight:600, padding:'2px 8px', borderRadius:99, background:`${status.color}14`, color:status.color, border:`1px solid ${status.color}33` }}>{status.text}</span>
          </div>
          <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:10 }}>
            {photo ? (
              <img src={photo} alt={name} style={{ height:32, width:32, borderRadius:'50%', objectFit:'cover', flexShrink:0, border:'1px solid rgba(255,255,255,0.1)' }} />
            ) : (
              <div style={{ height:32, width:32, borderRadius:'50%', background:'linear-gradient(135deg,#1d4ed8,#0ea5e9)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:13, fontWeight:700, color:'#fff', flexShrink:0 }}>{initial}</div>
            )}
            <div style={{ overflow:'hidden' }}>
              <div style={{ fontSize:12, fontWeight:600, color:'#cbd5e1', whiteSpace:'nowrap', textOverflow:'ellipsis', overflow:'hidden' }}>{name}</div>
              <div style={{ fontSize:11, color:'#475569', whiteSpace:'nowrap', textOverflow:'ellipsis', overflow:'hidden' }}>{title}</div>
            </div>
          </div>
          <button onClick={handleLogout} id="logout-btn" style={{ display:'flex', alignItems:'center', gap:6, width:'100%', padding:'7px 10px', borderRadius:10, border:'1px solid rgba(255,255,255,0.06)', background:'rgba(255,255,255,0.03)', color:'#64748b', fontSize:12, fontWeight:500, cursor:'pointer', transition:'all .15s' }}
            onMouseEnter={e => { e.currentTarget.style.color='#cbd5e1'; e.currentTarget.style.borderColor='rgba(148,163,184,.22)'; e.currentTarget.style.background='rgba(148,163,184,.08)' }}
            onMouseLeave={e => { e.currentTarget.style.color='#64748b'; e.currentTarget.style.borderColor='rgba(255,255,255,0.06)'; e.currentTarget.style.background='rgba(255,255,255,0.03)' }}
          >
            <LogOut size={12} /> Log out of Jobs Land
          </button>
        </div>
      </div>
    </aside>
  )
}
