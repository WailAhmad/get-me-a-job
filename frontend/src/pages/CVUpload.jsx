import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { uploadCV, getCV, clearCV } from '../api/client'
import { UploadCloud, CheckCircle, MessageSquare, FileText, RefreshCw, Award, Briefcase, Mail, Phone, MapPin, Clock, Sparkles, Shield } from 'lucide-react'

function InfoCard({ icon: Icon, label, value, color, children }) {
  return (
    <div style={{
      padding: 14, borderRadius: 14,
      background: `linear-gradient(135deg, ${color}08, ${color}04)`,
      border: `1px solid ${color}18`,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: children ? 10 : 0 }}>
        <div style={{
          width: 32, height: 32, borderRadius: 10,
          background: `${color}14`, display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Icon size={15} style={{ color }} />
        </div>
        <div>
          <div style={{ fontSize: 10, fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '.05em' }}>{label}</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)' }}>{value}</div>
        </div>
      </div>
      {children}
    </div>
  )
}

export default function CVUpload({ onUploaded }) {
  const navigate = useNavigate()
  const [cv, setCv] = useState(null)
  const [status, setStatus] = useState('')
  const [statusTone, setStatusTone] = useState('info')
  const [success, setSuccess] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)

  const refresh = async () => { try { const c = await getCV(); setCv(c) } catch {} }
  useEffect(() => { refresh() }, [])

  const upload = async (file) => {
    if (!file || busy) return
    setStatus('Uploading and parsing your CV...'); setStatusTone('info'); setSuccess(false); setBusy(true)
    try {
      const form = new FormData(); form.append('file', file)
      const r = await uploadCV(form)
      setStatus(r.message || 'CV uploaded.'); setStatusTone('success'); setSuccess(true)
      setCv(r.cv); onUploaded && onUploaded()
    } catch (e) { setStatus(`Error: ${e.message}`); setStatusTone('error'); setSuccess(false) }
    finally { setBusy(false) }
  }

  const replace = async () => { await clearCV(); setCv(null); setStatus(''); setSuccess(false) }

  const uploaded = cv?.uploaded

  return (
    <div className="animate-fade-in">
      <h1 className="page-title" style={{ marginBottom:4 }}>My CV</h1>
      <p className="page-subtitle" style={{ marginBottom:24 }}>Upload your CV once — we extract skills, experience, seniority, and contact details.</p>

      {!uploaded ? (
        <>
          <div className="card" style={{ textAlign:'center', padding:48, border:`2px dashed ${dragging?'#3b82f6':'rgba(255,255,255,0.12)'}`, background:dragging?'rgba(59,130,246,.05)':'transparent', transition:'all .2s', cursor:'pointer' }}
            onDragOver={e=>{e.preventDefault();setDragging(true)}}
            onDragLeave={()=>setDragging(false)}
            onDrop={e=>{e.preventDefault();setDragging(false);upload(e.dataTransfer.files[0])}}
            onClick={()=>document.getElementById('cv-file').click()}
          >
            <UploadCloud size={40} style={{ color:'#3b82f6', marginBottom:12 }} />
            <p style={{ fontSize:16, fontWeight:700, color:'var(--text)', marginBottom:6 }}>Drop your CV here</p>
            <p style={{ fontSize:13, color:'#64748b' }}>or click to browse · PDF, DOCX supported</p>
            <input id="cv-file" type="file" accept=".pdf,.docx,.doc" style={{ display:'none' }} onChange={e=>upload(e.target.files[0])} />
          </div>

          {status && (
            <div style={{
              marginTop:14, display:'flex', alignItems:'center', gap:8, padding:'12px 16px', borderRadius:14,
              background: statusTone === 'error' ? 'rgba(239,68,68,.08)' : statusTone === 'success' ? 'rgba(16,185,129,.08)' : 'rgba(59,130,246,.08)',
              border: `1px solid ${statusTone === 'error' ? 'rgba(239,68,68,.2)' : statusTone === 'success' ? 'rgba(16,185,129,.2)' : 'rgba(59,130,246,.2)'}`,
              fontSize:13, color: statusTone === 'error' ? '#f87171' : statusTone === 'success' ? '#34d399' : '#93c5fd'
            }}>
              {success && <CheckCircle size={14} />} {status}
            </div>
          )}
        </>
      ) : (
        <>
          {/* File header */}
          <div className="card" style={{ marginBottom:16 }}>
            <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:12 }}>
              <div style={{ display:'flex', gap:12, alignItems:'center' }}>
                <div style={{ height:44, width:44, borderRadius:12, background:'rgba(16,185,129,.16)', border:'1px solid rgba(16,185,129,.3)', display:'flex', alignItems:'center', justifyContent:'center' }}>
                  <FileText size={20} style={{ color:'#34d399' }} />
                </div>
                <div>
                  <div style={{ fontSize:15, fontWeight:700, color:'var(--text)' }}>{cv.filename}</div>
                  <div style={{ fontSize:12, color:'#64748b', marginTop:2 }}>
                    Parsed successfully · {cv.skills?.length||0} skills detected
                  </div>
                </div>
              </div>
              <button onClick={replace} style={{ display:'flex', alignItems:'center', gap:6, padding:'7px 12px', borderRadius:10, border:'1px solid rgba(255,255,255,0.08)', background:'rgba(255,255,255,0.03)', color:'#94a3b8', fontSize:12, cursor:'pointer' }}>
                <RefreshCw size={12} /> Replace CV
              </button>
            </div>
          </div>

          {/* Key metrics row */}
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(180px, 1fr))', gap:12, marginBottom:16 }}>
            <InfoCard icon={Shield} label="ATS Score" value={`${cv.ats_score || '—'}%`} color={cv.ats_score >= 80 ? '#10b981' : cv.ats_score >= 60 ? '#f59e0b' : '#ef4444'} />
            <InfoCard icon={Clock} label="Experience" value={`${cv.years} Years`} color="#3b82f6" />
            <InfoCard icon={Award} label="Seniority Level" value={cv.seniority || 'Professional'} color="#8b5cf6" />
            <InfoCard icon={Sparkles} label="Skills Detected" value={`${cv.skills?.length || 0} Skills`} color="#0ea5e9" />
          </div>

          {cv.ats_hints?.length > 0 && (
            <div className="card" style={{ marginBottom:16, border:'1px solid rgba(245,158,11,.22)', background:'rgba(245,158,11,.045)' }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#fbbf24', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 10 }}>
                ATS score hints
              </div>
              <div style={{ display:'grid', gap:8 }}>
                {cv.ats_hints.map((hint, i) => (
                  <div key={i} style={{ fontSize:13, color:'var(--text-secondary)', lineHeight:1.5, display:'flex', gap:8 }}>
                    <span style={{ color:'#f59e0b' }}>•</span>
                    <span>{hint}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Education */}
          {cv.education?.length > 0 && (
            <div className="card" style={{ marginBottom:16 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 12 }}>
                Education
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {cv.education.map(edu => (
                  <span key={edu} style={{
                    fontSize: 12, fontWeight: 600, padding: '6px 14px', borderRadius: 99,
                    background: 'rgba(139,92,246,.08)', color: '#c4b5fd', border: '1px solid rgba(139,92,246,.2)',
                  }}>🎓 {edu}</span>
                ))}
              </div>
            </div>
          )}

          {/* Contact details */}
          {cv.contact && Object.keys(cv.contact).length > 0 && (
            <div className="card" style={{ marginBottom:16 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 12 }}>
                Contact Details Detected
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
                {cv.contact.email && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px', borderRadius: 10, background: 'rgba(59,130,246,0.06)', border: '1px solid rgba(59,130,246,0.15)' }}>
                    <Mail size={14} style={{ color: '#3b82f6' }} />
                    <span style={{ fontSize: 13, color: '#93c5fd' }}>{cv.contact.email}</span>
                  </div>
                )}
                {cv.contact.phone && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px', borderRadius: 10, background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.15)' }}>
                    <Phone size={14} style={{ color: '#34d399' }} />
                    <span style={{ fontSize: 13, color: '#6ee7b7' }}>{cv.contact.phone}</span>
                  </div>
                )}
                {cv.contact.location && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px', borderRadius: 10, background: 'rgba(139,92,246,0.06)', border: '1px solid rgba(139,92,246,0.15)' }}>
                    <MapPin size={14} style={{ color: '#a78bfa' }} />
                    <span style={{ fontSize: 13, color: '#c4b5fd' }}>{cv.contact.location}</span>
                  </div>
                )}
                {(cv.contact.linkedin || cv.linkedin || cv.contact.linkedin_label || cv.linkedin_label) && (
                  <a href={cv.contact.linkedin || cv.linkedin || undefined} target={cv.contact.linkedin || cv.linkedin ? '_blank' : undefined} rel="noopener noreferrer"
                    onClick={(e) => { if (!(cv.contact.linkedin || cv.linkedin)) e.preventDefault() }}
                    style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px', borderRadius: 10, background: 'rgba(14,165,233,0.06)', border: '1px solid rgba(14,165,233,0.15)', textDecoration: 'none', cursor: (cv.contact.linkedin || cv.linkedin) ? 'pointer' : 'default' }}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="#38bdf8"><path d="M20.5 2h-17A1.5 1.5 0 002 3.5v17A1.5 1.5 0 003.5 22h17a1.5 1.5 0 001.5-1.5v-17A1.5 1.5 0 0020.5 2zM8 19H5v-9h3zM6.5 8.25A1.75 1.75 0 118.3 6.5a1.78 1.78 0 01-1.8 1.75zM19 19h-3v-4.74c0-1.42-.6-1.93-1.38-1.93A1.74 1.74 0 0013 14.19a.66.66 0 000 .14V19h-3v-9h2.9v1.3a3.11 3.11 0 012.7-1.4c1.55 0 3.36.86 3.36 3.66z"/></svg>
                    <span style={{ fontSize: 13, color: '#7dd3fc' }}>{cv.contact.linkedin_label || cv.linkedin_label || 'LinkedIn Profile'}</span>
                  </a>
                )}
              </div>
            </div>
          )}

          {/* Skills */}
          {cv.skills?.length > 0 && (
            <div className="card" style={{ marginBottom:16 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 12 }}>
                Skills & Competencies
              </div>
              <div style={{ display:'flex', flexWrap:'wrap', gap:6 }}>
                {cv.skills.map(s => (
                  <span key={s} style={{
                    fontSize:12, fontWeight:600, padding:'5px 12px', borderRadius:99,
                    background:'rgba(59,130,246,.08)', color:'#93c5fd', border:'1px solid rgba(59,130,246,.18)',
                    transition: 'all .2s',
                  }}>{s}</span>
                ))}
              </div>
            </div>
          )}

          {/* Experience items */}
          {cv.experience?.length > 0 && (
            <div className="card" style={{ marginBottom:16 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 12 }}>
                Key Experience
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {cv.experience.map((exp, i) => (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px',
                    borderRadius: 10, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)',
                  }}>
                    <Briefcase size={14} style={{ color: '#64748b', flexShrink: 0 }} />
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)' }}>{exp.title}</div>
                      <div style={{ fontSize: 11, color: '#64748b' }}>{exp.company}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* CV Summary text */}
          {cv.summary && (
            <div className="card" style={{ marginBottom:16 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 10 }}>
                CV Summary
              </div>
              <div style={{ fontSize:12, color:'#94a3b8', lineHeight:1.7, padding:12, borderRadius:10, background:'rgba(255,255,255,0.02)', border:'1px solid rgba(255,255,255,0.05)', whiteSpace: 'pre-wrap' }}>
                {cv.summary}
              </div>
            </div>
          )}

          {/* Next step CTA */}
          <div className="card" style={{ background:'linear-gradient(135deg,rgba(99,102,241,0.08),rgba(14,165,233,0.04))', border:'1px solid rgba(99,102,241,0.22)' }}>
            <div style={{ display:'flex', gap:14, alignItems:'center' }}>
              <div style={{ height:44, width:44, borderRadius:12, background:'rgba(99,102,241,.18)', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0 }}>
                <Sparkles size={20} style={{ color:'#818cf8' }} />
              </div>
              <div style={{ flex:1 }}>
                <div style={{ fontSize:15, fontWeight:700, color:'var(--text)', marginBottom:2 }}>Next: tell Jobby what you're looking for</div>
                <div style={{ fontSize:12, color:'#94a3b8' }}>Country, recency, and target roles — takes 30 seconds.</div>
              </div>
              <button onClick={() => navigate('/chat')} className="btn-primary" style={{ flexShrink:0, gap:6 }}>
                Open Jobby →
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
