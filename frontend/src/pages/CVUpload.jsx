import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { uploadCV, getCV, clearCV } from '../api/client'
import { UploadCloud, CheckCircle, MessageSquare, FileText, RefreshCw } from 'lucide-react'

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
      <p className="page-subtitle" style={{ marginBottom:24 }}>Upload your CV once — we extract skills and years of experience to match jobs semantically.</p>

      {!uploaded ? (
        <div className="card" style={{ textAlign:'center', padding:48, border:`2px dashed ${dragging?'#3b82f6':'rgba(255,255,255,0.12)'}`, background:dragging?'rgba(59,130,246,.05)':'transparent', transition:'all .2s', cursor:'pointer' }}
          onDragOver={e=>{e.preventDefault();setDragging(true)}}
          onDragLeave={()=>setDragging(false)}
          onDrop={e=>{e.preventDefault();setDragging(false);upload(e.dataTransfer.files[0])}}
          onClick={()=>document.getElementById('cv-file').click()}
        >
          <UploadCloud size={40} style={{ color:'#3b82f6', marginBottom:12 }} />
          <p style={{ fontSize:15, fontWeight:600, color:'#f1f5f9', marginBottom:6 }}>Drop your CV here</p>
          <p style={{ fontSize:13, color:'#64748b' }}>or click to browse · PDF, DOCX supported</p>
          <input id="cv-file" type="file" accept=".pdf,.docx,.doc" style={{ display:'none' }} onChange={e=>upload(e.target.files[0])} />
        </div>
      ) : (
        <>
          <div className="card" style={{ marginBottom:14 }}>
            <div style={{ display:'flex', alignItems:'flex-start', justifyContent:'space-between', gap:12, marginBottom:14 }}>
              <div style={{ display:'flex', gap:12, alignItems:'center' }}>
                <div style={{ height:42, width:42, borderRadius:12, background:'rgba(16,185,129,.16)', border:'1px solid rgba(16,185,129,.3)', display:'flex', alignItems:'center', justifyContent:'center' }}>
                  <FileText size={18} style={{ color:'#34d399' }} />
                </div>
                <div>
                  <div style={{ fontSize:14, fontWeight:600, color:'#f1f5f9' }}>{cv.filename}</div>
                  <div style={{ fontSize:12, color:'#64748b', marginTop:2 }}>Parsed · {cv.skills?.length||0} skills · {cv.years} years experience</div>
                </div>
              </div>
              <button onClick={replace} style={{ display:'flex', alignItems:'center', gap:6, padding:'7px 12px', borderRadius:10, border:'1px solid rgba(255,255,255,0.08)', background:'rgba(255,255,255,0.03)', color:'#94a3b8', fontSize:12, cursor:'pointer' }}>
                <RefreshCw size={12} /> Replace
              </button>
            </div>
            {cv.skills?.length > 0 && (
              <div style={{ display:'flex', flexWrap:'wrap', gap:6, marginBottom:14 }}>
                {cv.skills.map(s => (
                  <span key={s} style={{ fontSize:11, fontWeight:600, padding:'4px 10px', borderRadius:99, background:'rgba(59,130,246,.08)', color:'#93c5fd', border:'1px solid rgba(59,130,246,.18)' }}>{s}</span>
                ))}
              </div>
            )}
            {cv.summary && (
              <div style={{ fontSize:12, color:'#94a3b8', lineHeight:1.6, padding:12, borderRadius:10, background:'rgba(255,255,255,0.02)', border:'1px solid rgba(255,255,255,0.05)' }}>
                {cv.summary}
              </div>
            )}
          </div>

          <div className="card" style={{ background:'linear-gradient(135deg,rgba(20,184,166,0.08),rgba(56,189,248,0.04))', border:'1px solid rgba(20,184,166,0.22)' }}>
            <div style={{ display:'flex', gap:14, alignItems:'center' }}>
              <div style={{ height:44, width:44, borderRadius:12, background:'rgba(20,184,166,.18)', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0 }}>
                <MessageSquare size={20} style={{ color:'#2dd4bf' }} />
              </div>
              <div style={{ flex:1 }}>
                <div style={{ fontSize:14, fontWeight:600, color:'#f1f5f9', marginBottom:2 }}>Next: tell the AI Assistant what you're looking for</div>
                <div style={{ fontSize:12, color:'#94a3b8' }}>Country, recency, and target roles — takes 30 seconds.</div>
              </div>
              <button onClick={() => navigate('/chat')} className="btn-primary" style={{ flexShrink:0, gap:6 }}>
                Open AI Assistant →
              </button>
            </div>
          </div>
        </>
      )}

      {status && !uploaded && (
        <div style={{
          marginTop:14,
          display:'flex',
          alignItems:'center',
          gap:8,
          padding:'12px 16px',
          borderRadius:14,
          background:statusTone === 'error' ? 'rgba(239,68,68,.08)' : statusTone === 'success' ? 'rgba(16,185,129,.08)' : 'rgba(59,130,246,.08)',
          border:`1px solid ${statusTone === 'error' ? 'rgba(239,68,68,.2)' : statusTone === 'success' ? 'rgba(16,185,129,.2)' : 'rgba(59,130,246,.2)'}`,
          fontSize:13,
          color:statusTone === 'error' ? '#f87171' : statusTone === 'success' ? '#34d399' : '#93c5fd'
        }}>
          {success && <CheckCircle size={14} />} {status}
        </div>
      )}
    </div>
  )
}
