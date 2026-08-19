import { useState, useRef, useEffect } from 'react'
import {
  Search, Play, Pause, SkipBack, SkipForward, Layers, Eye,
  AlertTriangle, CheckCircle, XCircle, Car, Clock, FileText,
  Send,
} from 'lucide-react'
import { CLAIMS as MOCK_CLAIMS, AI_QA, type Claim } from '../../data/mock'
import { fetchAllClaims, getForensicAuditUrl } from '../../data/api'
import { StatusPill, RiskBadge, SectionHeading, Btn, C } from '../common/ui'

function apiClaimToLocal(c: any): Claim {
  const score = c.fraud_confidence_score ?? 0
  const status = score < 15 ? 'approved' : score <= 85 ? 'review' : 'siu'
  const findings = c.analyses?.flatMap((a: any) => {
    try { const d = JSON.parse(a.findings_json); return d.findings?.map((f: any) => f.detail) || [] } catch { return [] }
  }) || []
  const created = c.created_at ? new Date(c.created_at) : new Date()
  const diffMs = Date.now() - created.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  const timeAgo = diffMin < 60 ? `${diffMin}m ago` : `${Math.floor(diffMin / 60)}h ${diffMin % 60}m ago`

  return {
    id: c.claim_number,
    name: c.claimant_name || 'Unknown',
    score,
    status,
    time: timeAgo,
    isLive: c.status === 'processing',
    incidentType: 'Auto Collision',
    location: c.accident_location || '',
    description: c.accident_description || '',
    coverageType: 'Own Damage',
    findings,
    auditTrail: [{ time: created.toLocaleTimeString(), event: `Claim ${c.claim_number} received` }],
    hasVideo: !!c.video_url,
    hasAudio: !!c.audio_url,
    hasPhotos: !!c.video_url,
    hasPdf: (c.documents?.length || 0) > 0,
    fraudAmount: Math.round(score * 150),
    // Extra fields for media display
    _videoUrl: c.video_url,
    _audioUrl: c.audio_url,
    _backendId: c.id,
  } as Claim & { _videoUrl?: string; _audioUrl?: string; _backendId?: number }
}

function useLiveClaims() {
  const [liveClaims, setLiveClaims] = useState<Claim[]>([])

  useEffect(() => {
    let active = true
    const load = async () => {
      const data = await fetchAllClaims()
      if (active && Array.isArray(data)) {
        setLiveClaims(data.map(apiClaimToLocal))
      }
    }
    load()
    const interval = setInterval(load, 5000) // Poll every 5s
    return () => { active = false; clearInterval(interval) }
  }, [])

  return liveClaims
}

const CLAIMS_STATIC = MOCK_CLAIMS

// ── Mock claim images (stable per claim index) ─────────────────────────────
const EVIDENCE_IMAGES = [
  'https://images.unsplash.com/photo-1601362840469-51e4d8d58785?w=800&h=450&fit=crop&auto=format',
  'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800&h=450&fit=crop&auto=format',
  'https://images.unsplash.com/photo-1568605117036-5fe5e7bab0b7?w=800&h=450&fit=crop&auto=format',
  'https://images.unsplash.com/photo-1494976388531-d1058494cdd8?w=800&h=450&fit=crop&auto=format',
]

// ── Radial gauge ──────────────────────────────────────────────────────────────
function FraudGauge({ score }: { score: number }) {
  const r = 52, cx = 66, cy = 66, sw = 9, arcAngle = 240, startAngle = 150
  const toRad = (d: number) => (d * Math.PI) / 180
  const arc = (start: number, sweep: number) => {
    const s = toRad(start), e = toRad(start + sweep)
    const x1 = cx + r * Math.cos(s), y1 = cy + r * Math.sin(s)
    const x2 = cx + r * Math.cos(e), y2 = cy + r * Math.sin(e)
    return `M ${x1} ${y1} A ${r} ${r} 0 ${sweep > 180 ? 1 : 0} 1 ${x2} ${y2}`
  }
  const color = score < 15 ? C.green : score <= 85 ? C.amber : C.red
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <svg width={132} height={116} viewBox="0 0 132 116">
        <path d={arc(startAngle, arcAngle)} fill="none" stroke="#F1F5F9" strokeWidth={sw} strokeLinecap="round" />
        <path d={arc(startAngle, (score / 100) * arcAngle)} fill="none" stroke={color} strokeWidth={sw} strokeLinecap="round" />
        <text x={cx} y={cy - 5} textAnchor="middle" fontSize={24} fontWeight={800} fill={color} fontFamily="Inter, system-ui, sans-serif">{score}%</text>
        <text x={cx} y={cx + 13} textAnchor="middle" fontSize={8} fill="#94A3B8" fontFamily="Inter, system-ui, sans-serif" letterSpacing="0.06em">FRAUD SCORE</text>
      </svg>
      <StatusPill status={score < 15 ? 'approved' : score <= 85 ? 'review' : 'siu'} size="xs" />
    </div>
  )
}

// ── Frame timeline ────────────────────────────────────────────────────────────
function FrameTimeline({ showOverlay }: { showOverlay: boolean }) {
  const [pos, setPos] = useState(0.42)
  const ref = useRef<HTMLDivElement>(null)
  const markers = [0.18, 0.31, 0.42, 0.58, 0.71]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
        <span style={{ fontSize: 10, fontWeight: 600, color: C.muted }}>Timeline</span>
        <span style={{ fontSize: 10, color: C.mutedLight, fontFamily: 'monospace' }}>{Math.floor(pos * 42)}s / 42s</span>
      </div>
      <div
        ref={ref}
        onClick={e => {
          if (!ref.current) return
          const rect = ref.current.getBoundingClientRect()
          setPos(Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)))
        }}
        style={{ height: 30, background: '#F8FAFC', border: `1px solid ${C.border}`, borderRadius: 5, position: 'relative', cursor: 'pointer', overflow: 'hidden' }}
      >
        <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${pos * 100}%`, background: 'rgba(37,99,235,0.06)', borderRight: '2px solid #2563EB' }} />
        {showOverlay && markers.map((m, i) => (
          <div key={i} style={{ position: 'absolute', left: `${m * 100}%`, top: 0, bottom: 0, width: 2, background: '#EF4444', opacity: 0.7 }} />
        ))}
        <div style={{ position: 'absolute', left: `${pos * 100}%`, top: '50%', transform: 'translate(-50%,-50%)', width: 11, height: 11, background: '#2563EB', borderRadius: '50%', border: '2px solid #fff', boxShadow: '0 1px 4px rgba(37,99,235,0.3)' }} />
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', gap: 0, padding: '0 2px', opacity: 0.1 }}>
          {Array.from({ length: 80 }).map((_, i) => (
            <div key={i} style={{ flex: 1, height: `${18 + Math.sin(i * 0.4) * 12}%`, background: '#64748B', borderRadius: 1 }} />
          ))}
        </div>
      </div>
      {showOverlay && <div style={{ fontSize: 9, color: C.mutedLight, marginTop: 4, display: 'flex', alignItems: 'center', gap: 4 }}><div style={{ width: 7, height: 7, background: C.red, borderRadius: 1 }} /> 5 anomaly frames · click to navigate</div>}
    </div>
  )
}

// ── AI Copilot chat ───────────────────────────────────────────────────────────
const SUGGESTED = ['Why was this flagged?', 'Show audio analysis', 'Compare to similar claims', 'What evidence is most suspicious?']

interface ChatMsg { from: 'user' | 'ai'; text: string }

function AICopilot({ claim }: { claim: Claim }) {
  const backendId = (claim as any)._backendId
  const [messages, setMessages] = useState<ChatMsg[]>([
    { from: 'ai', text: `I've completed multi-modal analysis on ${claim.id}. Ask me anything about the findings, or click a suggested question below.` },
  ])
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)
  const chatContainerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight
    }
  }, [messages, typing])

  const ask = async (q: string) => {
    if (!q.trim()) return
    const userMsg: ChatMsg = { from: 'user', text: q }
    setMessages(m => [...m, userMsg])
    setInput('')
    setTyping(true)

    if (backendId) {
      try {
        const res = await fetch(`http://localhost:8000/claims/${backendId}/copilot-chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ officer_id: 1, message: q }),
        })
        const data = await res.json()
        setTyping(false)
        setMessages(m => [...m, { from: 'ai', text: data.response || 'No response.' }])
      } catch {
        setTyping(false)
        setMessages(m => [...m, { from: 'ai', text: 'Failed to reach the AI copilot. Is the backend running?' }])
      }
    } else {
      // Fallback to mock for static demo claims
      const key = Object.keys(AI_QA).find(k => q.toLowerCase().includes(k)) ?? 'default'
      setTimeout(() => {
        setTyping(false)
        setMessages(m => [...m, { from: 'ai', text: AI_QA[key] }])
      }, 800)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 240 }}>
      {/* Messages */}
      <div ref={chatContainerRef} style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8, paddingBottom: 4 }}>
        {messages.map((m, i) => (
          <div key={i} style={{ display: 'flex', justifyContent: m.from === 'user' ? 'flex-end' : 'flex-start' }}>
            <div style={{
              maxWidth: '85%', padding: '7px 10px', borderRadius: m.from === 'user' ? '10px 10px 2px 10px' : '10px 10px 10px 2px',
              background: m.from === 'user' ? '#EFF6FF' : '#F8FAFC',
              border: `1px solid ${m.from === 'user' ? '#BFDBFE' : C.border}`,
              fontSize: 11, lineHeight: 1.5, color: m.from === 'user' ? '#1E40AF' : C.text,
            }}>
              {m.text}
            </div>
          </div>
        ))}
        {typing && (
          <div style={{ display: 'flex', gap: 4, alignItems: 'center', padding: '7px 10px', background: '#F8FAFC', border: `1px solid ${C.border}`, borderRadius: '10px 10px 10px 2px', width: 52 }}>
            {[0, 0.2, 0.4].map((d, i) => (
              <div key={i} style={{ width: 5, height: 5, borderRadius: '50%', background: C.mutedLight, animation: `wave-bar 0.7s ${d}s ease-in-out infinite alternate` }} />
            ))}
          </div>
        )}
        <div ref={endRef} />
      </div>
      {/* Suggested chips */}
      <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 4, paddingTop: 6, paddingBottom: 6 }}>
        {SUGGESTED.map(q => (
          <button key={q} onClick={() => ask(q)} style={{ fontSize: 10, padding: '3px 8px', borderRadius: 20, background: '#EFF6FF', border: '1px solid #BFDBFE', color: '#2563EB', cursor: 'pointer', fontFamily: 'inherit' }}>
            {q}
          </button>
        ))}
      </div>
      {/* Input */}
      <div style={{ display: 'flex', gap: 6 }}>
        <input
          value={input} onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && ask(input)}
          placeholder="Ask the AI a question…"
          style={{ flex: 1, height: 32, background: '#F8FAFC', border: `1px solid ${C.border}`, borderRadius: 7, fontSize: 11, padding: '0 10px', outline: 'none', fontFamily: 'inherit', color: C.text }}
        />
        <button onClick={() => ask(input)} style={{ width: 32, height: 32, borderRadius: 7, background: C.blue, border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Send size={13} color="#fff" />
        </button>
      </div>
    </div>
  )
}

// ── SIU Quorum Voting ─────────────────────────────────────────────────────────
const OFFICERS = [
  { name: 'D. Torres',   role: 'SIU Investigator' },
  { name: 'R. Park',     role: 'Senior Adjuster' },
  { name: 'S. Okonkwo', role: 'Fraud Analyst' },
  { name: 'M. Reyes',   role: 'SIU Lead' },
]

function SIUVoting() {
  const [votes, setVotes] = useState<(null | 'fraud' | 'clear')[]>([null, null, null, null])
  const [notes, setNotes] = useState(['', '', '', ''])
  const [finalized, setFinalized] = useState(false)

  const castCount = votes.filter(v => v !== null).length
  const fraudVotes = votes.filter(v => v === 'fraud').length

  const setVote = (i: number, v: 'fraud' | 'clear') => {
    const next = [...votes]; next[i] = next[i] === v ? null : v; setVotes(next)
  }
  const setNote = (i: number, s: string) => { const n = [...notes]; n[i] = s; setNotes(n) }

  if (finalized) {
    const confirmed = fraudVotes >= 3
    return (
      <div style={{ background: confirmed ? '#FFF5F5' : '#F0FDF4', border: `1px solid ${confirmed ? '#FECACA' : '#BBF7D0'}`, borderRadius: 8, padding: '14px', textAlign: 'center' }}>
        {confirmed ? <XCircle size={20} color={C.red} style={{ marginBottom: 6 }} /> : <CheckCircle size={20} color={C.green} style={{ marginBottom: 6 }} />}
        <div style={{ fontSize: 13, fontWeight: 700, color: confirmed ? C.red : C.green }}>
          {confirmed ? 'Fraud Confirmed — Claim Denied' : 'Claim Cleared — No Fraud Found'}
        </div>
        <div style={{ fontSize: 10, color: C.muted, marginTop: 4 }}>Final vote: {fraudVotes} Confirm Fraud · {4 - fraudVotes} Clear</div>
      </div>
    )
  }

  return (
    <div>
      <div style={{ background: '#FFF5F5', border: `1px solid #FECACA`, borderRadius: 8, padding: '8px 12px', marginBottom: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: C.red }}>SIU Quorum Required</span>
        <span style={{ fontSize: 11, color: C.muted }}>{castCount} of 4 votes cast</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {OFFICERS.map((o, i) => (
          <div key={i} style={{ border: `1px solid ${C.border}`, borderRadius: 8, padding: '10px 12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: votes[i] !== null ? 8 : 0 }}>
              <div>
                <div style={{ fontSize: 11, fontWeight: 600, color: C.text }}>{o.name}</div>
                <div style={{ fontSize: 9, color: C.mutedLight }}>{o.role}</div>
              </div>
              <div style={{ display: 'flex', gap: 4 }}>
                <button onClick={() => setVote(i, 'fraud')} style={{ fontSize: 10, padding: '3px 8px', borderRadius: 6, border: `1px solid ${votes[i] === 'fraud' ? C.red : C.border}`, background: votes[i] === 'fraud' ? '#FFF5F5' : '#fff', color: votes[i] === 'fraud' ? C.red : C.muted, cursor: 'pointer', fontWeight: votes[i] === 'fraud' ? 700 : 400 }}>
                  Confirm Fraud
                </button>
                <button onClick={() => setVote(i, 'clear')} style={{ fontSize: 10, padding: '3px 8px', borderRadius: 6, border: `1px solid ${votes[i] === 'clear' ? C.green : C.border}`, background: votes[i] === 'clear' ? '#F0FDF4' : '#fff', color: votes[i] === 'clear' ? C.green : C.muted, cursor: 'pointer', fontWeight: votes[i] === 'clear' ? 700 : 400 }}>
                  Clear
                </button>
              </div>
            </div>
            {votes[i] !== null && (
              <input
                value={notes[i]} onChange={e => setNote(i, e.target.value)}
                placeholder="Optional notes…"
                style={{ width: '100%', boxSizing: 'border-box' as const, fontSize: 10, padding: '5px 8px', borderRadius: 5, border: `1px solid ${C.border}`, background: '#F8FAFC', color: C.text, outline: 'none', fontFamily: 'inherit' }}
              />
            )}
          </div>
        ))}
      </div>
      {castCount === 4 && (
        <button onClick={() => setFinalized(true)} style={{ width: '100%', marginTop: 10, padding: '10px', borderRadius: 8, border: 'none', cursor: 'pointer', background: fraudVotes >= 3 ? C.red : C.green, color: '#fff', fontSize: 12, fontWeight: 700 }}>
          Finalize Case — {fraudVotes >= 3 ? 'Confirm Fraud' : 'Clear Claim'}
        </button>
      )}
    </div>
  )
}

// ── Moderator Actions ─────────────────────────────────────────────────────────
function ModeratorActions() {
  const [state, setState] = useState<'idle' | 'rejecting' | 'approved' | 'rejected'>('idle')
  const [reason, setReason] = useState('')

  if (state === 'approved') return (
    <div style={{ background: '#F0FDF4', border: '1px solid #BBF7D0', borderRadius: 8, padding: '14px', display: 'flex', gap: 10, alignItems: 'center' }}>
      <CheckCircle size={18} color={C.green} />
      <div>
        <div style={{ fontSize: 12, fontWeight: 700, color: C.text }}>Claim Approved</div>
        <div style={{ fontSize: 10, color: C.muted, marginTop: 2 }}>Logged by K. Rodriguez · {new Date().toLocaleTimeString()}</div>
      </div>
    </div>
  )

  if (state === 'rejected') return (
    <div style={{ background: '#FFF5F5', border: '1px solid #FECACA', borderRadius: 8, padding: '14px', display: 'flex', gap: 10, alignItems: 'center' }}>
      <XCircle size={18} color={C.red} />
      <div>
        <div style={{ fontSize: 12, fontWeight: 700, color: C.text }}>Claim Rejected</div>
        <div style={{ fontSize: 10, color: C.muted, marginTop: 2 }}>Reason: {reason || '(no reason given)'}</div>
      </div>
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <Btn fullWidth variant="success" onClick={() => setState('approved')}>
        <CheckCircle size={13} /> Approve Claim
      </Btn>
      {state === 'rejecting'
        ? (
          <div>
            <textarea
              value={reason} onChange={e => setReason(e.target.value)}
              placeholder="Enter rejection reason…"
              rows={2}
              style={{ width: '100%', boxSizing: 'border-box' as const, padding: '8px 10px', fontSize: 12, borderRadius: 7, border: `1px solid ${C.border}`, outline: 'none', fontFamily: 'inherit', color: C.text, resize: 'none' as const, marginBottom: 6 }}
            />
            <div style={{ display: 'flex', gap: 6 }}>
              <Btn variant="outline" size="sm" onClick={() => setState('idle')} style={{ flex: 1 }}>Cancel</Btn>
              <Btn variant="danger" size="sm" onClick={() => setState('rejected')} style={{ flex: 1 }}>Confirm Rejection</Btn>
            </div>
          </div>
        )
        : <Btn fullWidth variant="danger" onClick={() => setState('rejecting')}><XCircle size={13} /> Reject Claim</Btn>
      }
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Main: ClaimsQueue
// ═══════════════════════════════════════════════════════════════════════════════
export default function ClaimsQueue({ headerSearch }: { headerSearch: string }) {
  const liveClaims = useLiveClaims()
  const CLAIMS = [...liveClaims, ...CLAIMS_STATIC]
  const [selected, setSelected] = useState(CLAIMS[0]?.id || '')
  const [filter, setFilter] = useState<'all' | 'high' | 'medium' | 'low'>('all')
  const [search, setSearch] = useState('')
  const [showOverlay, setShowOverlay] = useState(true)
  const [playing, setPlaying] = useState(false)
  const [rightSection, setRightSection] = useState<'analysis' | 'copilot' | 'voting'>('analysis')

  const q = headerSearch || search
  const visible = CLAIMS.filter(c => {
    const rm = filter === 'all' || (filter === 'high' && c.score > 85) || (filter === 'medium' && c.score >= 15 && c.score <= 85) || (filter === 'low' && c.score < 15)
    const sm = !q || c.name.toLowerCase().includes(q.toLowerCase()) || c.id.toLowerCase().includes(q.toLowerCase())
    return rm && sm
  })

  const claim = CLAIMS.find(c => c.id === selected) ?? CLAIMS[0]

  return (
    <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '272px 1fr 304px', overflow: 'hidden', minHeight: 0 }}>

      {/* ── LEFT: Claim list ───────────────────────────────────────────────── */}
      <div style={{ background: '#fff', borderRight: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ padding: '12px 12px 10px', borderBottom: `1px solid ${C.border}` }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span style={{ fontSize: 12, fontWeight: 700 }}>Priority Queue</span>
            <span style={{ fontSize: 10, background: '#FFF5F5', color: C.red, border: '1px solid #FECACA', borderRadius: 5, padding: '1px 7px', fontWeight: 700 }}>
              {CLAIMS.filter(c => c.score > 85).length} Critical
            </span>
          </div>
          <div style={{ position: 'relative', marginBottom: 8 }}>
            <Search size={11} color={C.mutedLight} style={{ position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)' }} />
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search…" style={{ width: '100%', height: 30, background: C.bg, border: `1px solid ${C.border}`, borderRadius: 6, fontSize: 11, padding: '0 8px 0 26px', outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' as const, color: C.text }} />
          </div>
          <div style={{ display: 'flex', gap: 3 }}>
            {(['all', 'high', 'medium', 'low'] as const).map(f => (
              <button key={f} onClick={() => setFilter(f)} style={{ flex: 1, padding: '3px 0', borderRadius: 5, fontSize: 9, fontWeight: 600, border: `1px solid ${filter === f ? C.blue : C.border}`, background: filter === f ? '#EFF6FF' : '#fff', color: filter === f ? C.blue : C.muted, cursor: 'pointer', textTransform: 'capitalize' as const }}>
                {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
              </button>
            ))}
          </div>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: 8 }}>
          {visible.map(c => {
            const sel = selected === c.id
            return (
              <div key={c.id} onClick={() => setSelected(c.id)} style={{ borderRadius: 8, padding: '10px 11px', marginBottom: 4, border: `1px solid ${sel ? '#BFDBFE' : '#F1F5F9'}`, background: sel ? '#EFF6FF' : '#fff', cursor: 'pointer', transition: 'all 0.15s' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 5 }}>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 600, color: C.text }}>{c.name}</div>
                    <div style={{ fontSize: 9, color: C.mutedLight, fontFamily: 'monospace', marginTop: 1 }}>{c.id}</div>
                  </div>
                  <RiskBadge score={c.score} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                    <Car size={9} color="#CBD5E1" />
                    <span style={{ fontSize: 10, color: C.mutedLight }}>{c.incidentType}</span>
                    {c.isLive && <span style={{ fontSize: 8, fontWeight: 700, background: '#FEE2E2', color: C.red, border: '1px solid #FECACA', borderRadius: 3, padding: '0 4px' }}>LIVE</span>}
                  </div>
                  <div style={{ display: 'flex', gap: 2, alignItems: 'center' }}>
                    <Clock size={9} color="#CBD5E1" />
                    <span style={{ fontSize: 9, color: '#CBD5E1' }}>{c.time}</span>
                  </div>
                </div>
                <div style={{ height: 2, background: '#F1F5F9', borderRadius: 1, marginTop: 7, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${c.score}%`, background: c.score > 85 ? C.red : c.score >= 15 ? C.amber : C.green, borderRadius: 1 }} />
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* ── CENTER: Media workspace ────────────────────────────────────────── */}
      <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', borderRight: `1px solid ${C.border}`, background: C.bg }}>
        <div style={{ padding: '10px 16px', background: '#fff', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 700 }}>Media Forensic Workspace</div>
            <div style={{ fontSize: 10, color: C.mutedLight, fontFamily: 'monospace', marginTop: 1 }}>{claim.id} · {claim.name} · {claim.incidentType}</div>
          </div>
          {/* Overlay toggle */}
          <button onClick={() => setShowOverlay(v => !v)} style={{ display: 'flex', alignItems: 'center', gap: 7, background: showOverlay ? '#EFF6FF' : '#fff', border: `1px solid ${showOverlay ? '#BFDBFE' : C.border}`, borderRadius: 7, padding: '5px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, color: showOverlay ? C.blue : C.muted }}>
            {showOverlay ? <Layers size={13} /> : <Eye size={13} />}
            {showOverlay ? 'Heatmap ON' : 'Heatmap OFF'}
          </button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* Video/Image player — real media for live claims */}
          {claim.hasVideo && (
            <div style={{ borderRadius: 10, overflow: 'hidden', background: '#000', position: 'relative', aspectRatio: '16/9', border: `1px solid ${C.border}` }}>
              {(claim as any)._videoUrl ? (
                (() => {
                  const url = (claim as any)._videoUrl as string
                  const isVideo = /\.(mp4|webm|mov|avi)$/i.test(url)
                  return isVideo ? (
                    <video src={url} controls style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }} />
                  ) : (
                    <img src={url} alt="Uploaded evidence" style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }} />
                  )
                })()
              ) : (
                <img src={EVIDENCE_IMAGES[0]} alt="Claim damage evidence" style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block', opacity: 0.88 }} />
              )}
              {showOverlay && claim.score > 50 && (
                <>
                  <div style={{ position: 'absolute', bottom: '18%', left: '12%', width: '40%', height: '30%', background: 'rgba(239,68,68,0.1)', border: '1.5px solid #EF4444', borderRadius: 4, pointerEvents: 'none' }}>
                    <div style={{ position: 'absolute', top: -20, left: 0, background: '#EF4444', borderRadius: '3px 3px 3px 0', padding: '2px 6px', fontSize: 8, fontFamily: 'monospace', color: '#fff', whiteSpace: 'nowrap' as const, display: 'flex', alignItems: 'center', gap: 3 }}>
                      <AlertTriangle size={8} /> BUMPER · Diffusion artifact · 91%
                    </div>
                  </div>
                  <div style={{ position: 'absolute', top: 10, left: 10, background: 'rgba(239,68,68,0.88)', borderRadius: 5, padding: '3px 8px', display: 'flex', alignItems: 'center', gap: 4 }}>
                    <Layers size={10} color="#fff" />
                    <span style={{ fontSize: 9, color: '#fff', fontFamily: 'monospace' }}>AI HEATMAP ACTIVE</span>
                  </div>
                </>
              )}
              {!showOverlay && (
                <div style={{ position: 'absolute', top: 10, left: 10, background: 'rgba(0,0,0,0.5)', borderRadius: 5, padding: '3px 8px', display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Eye size={10} color="rgba(255,255,255,0.8)" />
                  <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.8)', fontFamily: 'monospace' }}>RAW VIEW</span>
                </div>
              )}
              <div style={{ position: 'absolute', top: 10, right: 10, background: 'rgba(0,0,0,0.55)', borderRadius: 6, padding: '4px 8px', textAlign: 'center' }}>
                <div style={{ fontSize: 7, color: 'rgba(255,255,255,0.5)' }}>RISK</div>
                <div style={{ fontSize: 16, fontWeight: 800, color: claim.score > 85 ? C.red : claim.score >= 15 ? C.amber : C.green, fontFamily: 'monospace' }}>{claim.score}%</div>
              </div>
              {/* Controls */}
              <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, background: 'linear-gradient(to top,rgba(0,0,0,0.6),transparent)', padding: '16px 12px 10px', display: 'flex', alignItems: 'center', gap: 8 }}>
                <button style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}><SkipBack size={13} color="rgba(255,255,255,0.7)" /></button>
                <button onClick={() => setPlaying(v => !v)} style={{ width: 28, height: 28, borderRadius: '50%', background: 'rgba(255,255,255,0.15)', border: '1px solid rgba(255,255,255,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
                  {playing ? <Pause size={11} color="#fff" /> : <Play size={11} color="#fff" />}
                </button>
                <button style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}><SkipForward size={13} color="rgba(255,255,255,0.7)" /></button>
                <div style={{ flex: 1, height: 2, background: 'rgba(255,255,255,0.2)', borderRadius: 1 }}>
                  <div style={{ width: '42%', height: '100%', background: '#fff', borderRadius: 1 }} />
                </div>
                <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.6)', fontFamily: 'monospace' }}>0:18 / 0:42</span>
              </div>
            </div>
          )}

          {/* Frame timeline */}
          {claim.hasVideo && (
            <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 8, padding: '12px 14px' }}>
              <FrameTimeline showOverlay={showOverlay && claim.score > 50} />
            </div>
          )}

          {/* Audio player */}
          {claim.hasAudio && (
            <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 8, padding: '12px 14px' }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: 'uppercase' as const, letterSpacing: '0.06em', marginBottom: 8 }}>Voice Statement</div>
              {(claim as any)._audioUrl ? (
                <audio controls style={{ width: '100%', height: 36 }} src={(claim as any)._audioUrl}>
                  Your browser does not support audio playback.
                </audio>
              ) : (
                <div style={{ background: '#F8FAFC', borderRadius: 6, padding: '8px 10px', position: 'relative', overflow: 'hidden' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 1, height: 28 }}>
                    {Array.from({ length: 64 }).map((_, i) => (
                      <div key={i} style={{ flex: 1, height: `${12 + Math.sin(i * 0.5) * 9}px`, background: i >= 16 && i <= 24 && claim.score > 50 ? '#EF4444' : '#CBD5E1', borderRadius: 1 }} />
                    ))}
                  </div>
                  {claim.score > 50 && (
                    <div style={{ position: 'absolute', top: 0, bottom: 0, left: `${(16 / 64) * 100}%`, width: `${(8 / 64) * 100}%`, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: 2 }} />
                  )}
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 3 }}>
                    <span style={{ fontSize: 7, color: C.mutedLight, fontFamily: 'monospace' }}>0:00</span>
                    {claim.score > 50 && <span style={{ fontSize: 7, color: C.red, fontFamily: 'monospace' }}>⚠ 0:03–0:07</span>}
                    <span style={{ fontSize: 7, color: C.mutedLight, fontFamily: 'monospace' }}>0:42</span>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Photo gallery */}
          {claim.hasPhotos && (
            <div>
              <SectionHeading>Photo Evidence</SectionHeading>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
                {EVIDENCE_IMAGES.slice(0, 3).map((url, i) => (
                  <div key={i} style={{ borderRadius: 7, overflow: 'hidden', border: `1px solid ${i === 0 && claim.score > 50 ? '#FCA5A5' : C.border}`, position: 'relative', cursor: 'pointer' }}>
                    <img src={url} alt={`Evidence ${i + 1}`} style={{ width: '100%', aspectRatio: '4/3', objectFit: 'cover', display: 'block' }} />
                    {i === 0 && claim.score > 50 && (
                      <div style={{ position: 'absolute', top: 3, right: 3, width: 13, height: 13, background: C.red, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <AlertTriangle size={7} color="#fff" />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* PDF */}
          {claim.hasPdf && (
            <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 8, padding: '12px 14px', display: 'flex', gap: 10, alignItems: 'center' }}>
              <FileText size={16} color={C.muted} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: C.text }}>police_report.pdf</div>
                <div style={{ fontSize: 9, color: C.mutedLight }}>Supporting document · 2.4 MB</div>
              </div>
              <button style={{ fontSize: 11, padding: '4px 10px', borderRadius: 6, border: `1px solid ${C.border}`, background: '#fff', color: C.muted, cursor: 'pointer' }}>View</button>
            </div>
          )}
        </div>
      </div>

      {/* ── RIGHT: Analysis & Actions ──────────────────────────────────────── */}
      <div style={{ background: '#fff', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ padding: '10px 14px', borderBottom: `1px solid ${C.border}`, flexShrink: 0 }}>
          <div style={{ fontSize: 12, fontWeight: 700 }}>AI Analysis</div>
          <div style={{ fontSize: 9, color: C.mutedLight, fontFamily: 'monospace', marginTop: 1 }}>Model v3.2.1 · 08:18:04 PST</div>
          {/* Sub-nav */}
          <div style={{ display: 'flex', gap: 2, marginTop: 8 }}>
            {([['analysis', 'Findings'], ['copilot', 'AI Copilot'], ['voting', claim.status === 'siu' ? 'SIU Vote' : 'Actions']] as const).map(([id, label]) => (
              <button key={id} onClick={() => setRightSection(id as typeof rightSection)} style={{ flex: 1, padding: '4px 0', borderRadius: 5, border: `1px solid ${rightSection === id ? C.blue : C.border}`, background: rightSection === id ? '#EFF6FF' : '#fff', color: rightSection === id ? C.blue : C.muted, fontSize: 10, fontWeight: rightSection === id ? 700 : 400, cursor: 'pointer' }}>
                {label}
              </button>
            ))}
          </div>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 12 }}>

          {/* ── Findings section ── */}
          {rightSection === 'analysis' && (
            <>
              {/* Gauge */}
              <div style={{ background: claim.score > 85 ? '#FFF5F5' : claim.score >= 15 ? '#FFFBEB' : '#F0FDF4', border: `1px solid ${claim.score > 85 ? '#FECACA' : claim.score >= 15 ? '#FDE68A' : '#BBF7D0'}`, borderRadius: 10, padding: '14px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                <FraudGauge score={claim.score} />
                <div style={{ display: 'flex', gap: 16, marginTop: 6 }}>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 13, fontWeight: 800, color: C.text }}>99.1%</div>
                    <div style={{ fontSize: 8, color: C.mutedLight, textTransform: 'uppercase' as const }}>Confidence</div>
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 13, fontWeight: 800, color: C.text }}>7 AI</div>
                    <div style={{ fontSize: 8, color: C.mutedLight, textTransform: 'uppercase' as const }}>Models</div>
                  </div>
                </div>
              </div>

              {/* AI Findings */}
              <div>
                <SectionHeading>AI Findings</SectionHeading>
                {claim.findings.length === 0
                  ? <div style={{ fontSize: 11, color: C.muted, background: '#F0FDF4', border: '1px solid #BBF7D0', borderRadius: 8, padding: '10px 12px' }}>No anomalies detected — all signals within normal parameters.</div>
                  : claim.findings.map((f, i) => (
                    <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', padding: '8px 10px', background: '#FFF5F5', border: '1px solid #FECACA', borderRadius: 7, marginBottom: 6 }}>
                      <AlertTriangle size={13} color={C.red} style={{ flexShrink: 0, marginTop: 1 }} />
                      <span style={{ fontSize: 11, color: C.textSub, lineHeight: 1.5 }}>{f}</span>
                    </div>
                  ))
                }
              </div>

              {/* Audit trail */}
              <div>
                <SectionHeading>Audit Trail</SectionHeading>
                <div style={{ border: `1px solid ${C.border}`, borderRadius: 8, overflow: 'hidden' }}>
                  {claim.auditTrail.map((e, i, a) => (
                    <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', padding: '8px 12px', borderBottom: i < a.length - 1 ? `1px solid #F8FAFC` : 'none' }}>
                      <div style={{ width: 6, height: 6, borderRadius: '50%', background: i === 0 ? C.green : C.primary, marginTop: 3, flexShrink: 0 }} />
                      <span style={{ fontSize: 9, color: C.mutedLight, fontFamily: 'monospace', flexShrink: 0 }}>{e.time}</span>
                      <span style={{ fontSize: 10, color: C.textSub, lineHeight: 1.4 }}>{e.event}</span>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}

          {/* ── AI Copilot ── */}
          {rightSection === 'copilot' && (
            <>
              <div style={{ background: '#EFF6FF', border: '1px solid #BFDBFE', borderRadius: 8, padding: '8px 12px', fontSize: 11, color: '#1E40AF' }}>
                AI Copilot is scoped to <strong>{claim.id}</strong>. Ask anything about this claim's findings.
              </div>
              <AICopilot key={claim.id} claim={claim} />
            </>
          )}

          {/* ── Actions / Voting ── */}
          {rightSection === 'voting' && (
            <>
              {claim.status === 'siu' && <SIUVoting key={claim.id} />}
              {claim.status === 'review' && <ModeratorActions key={claim.id} />}
              {claim.status === 'approved' && (
                <div style={{ background: '#F0FDF4', border: '1px solid #BBF7D0', borderRadius: 8, padding: '14px', textAlign: 'center' }}>
                  <CheckCircle size={20} color={C.green} style={{ marginBottom: 6 }} />
                  <div style={{ fontSize: 12, fontWeight: 700, color: C.text }}>Auto-Approved</div>
                  <div style={{ fontSize: 10, color: C.muted, marginTop: 4 }}>This claim was automatically approved — no moderator action required.</div>
                </div>
              )}
              <div style={{ marginTop: 4 }}>
                {(claim as any)._backendId ? (
                  <a href={getForensicAuditUrl((claim as any)._backendId)} target="_blank" rel="noopener noreferrer" style={{ textDecoration: 'none', display: 'block' }}>
                    <Btn fullWidth variant="outline" size="sm">
                      <FileText size={13} /> Export PDF Forensic Audit Report
                    </Btn>
                  </a>
                ) : (
                  <Btn fullWidth variant="outline" size="sm" disabled>
                    <FileText size={13} /> Export PDF (submit via app first)
                  </Btn>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
