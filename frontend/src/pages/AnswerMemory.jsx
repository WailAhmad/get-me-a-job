import { useState, useEffect } from 'react'
import { getAnswers, deleteAnswer, saveAnswer } from '../api/client'
import { BookOpen, Trash2, Plus } from 'lucide-react'

export default function AnswerMemory() {
  const [answers, setAnswers] = useState([])
  const [q, setQ] = useState(''); const [a, setA] = useState('')
  const load = () => getAnswers().then(setAnswers).catch(()=>{})
  useEffect(() => { load() }, [])
  const remove = async (id) => { await deleteAnswer(id); load() }
  const add = async () => { if (!q.trim() || !a.trim()) return; await saveAnswer({ question:q.trim(), answer:a.trim() }); setQ(''); setA(''); load() }

  return (
    <div className="animate-fade-in">
      <h1 className="page-title">Answer Memory</h1>
      <p className="page-subtitle" style={{ marginBottom:20 }}>Saved Q&A — the bot reuses these to answer recurring application questions automatically.</p>

      <div className="card" style={{ marginBottom:14 }}>
        <div style={{ fontSize:12, fontWeight:600, color:'#94a3b8', marginBottom:10, textTransform:'uppercase', letterSpacing:'.06em' }}>Add answer</div>
        <input value={q} onChange={e=>setQ(e.target.value)} placeholder='Question (e.g. "What is your notice period?")' style={{ width:'100%', marginBottom:8 }}/>
        <textarea value={a} onChange={e=>setA(e.target.value)} placeholder="Your answer" rows={2} style={{ width:'100%', resize:'vertical', marginBottom:10 }}/>
        <button onClick={add} className="btn-primary" style={{ gap:6 }}><Plus size={13}/> Save to memory</button>
      </div>

      {answers.length === 0
        ? <div className="card" style={{ textAlign:'center', padding:40 }}><BookOpen size={32} style={{ color:'#475569', marginBottom:10 }} /><p style={{ color:'#64748b' }}>No saved answers yet — they appear automatically as you answer pending questions.</p></div>
        : <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
            {answers.map((ans, idx) => (
              <div key={`${ans.id || 'answer'}-${ans.question || idx}`} className="card" style={{ display:'flex', justifyContent:'space-between', gap:12 }}>
                <div style={{ minWidth:0 }}>
                  <div style={{ fontSize:12, fontWeight:600, color:'#94a3b8', marginBottom:4 }}>{ans.question}</div>
                  <div style={{ fontSize:14, color:'var(--text)' }}>{ans.answer}</div>
                </div>
                <button onClick={()=>remove(ans.id)} style={{ background:'none', border:'none', color:'#475569', cursor:'pointer', flexShrink:0 }}><Trash2 size={14} /></button>
              </div>
            ))}
          </div>}
    </div>
  )
}
