import { useState, useRef, useEffect } from 'react'
import {
  Search, Layers, Eye, AlertTriangle, CheckCircle, XCircle,
  Car, Clock, FileText, Send, Inbox, Loader,
} from 'lucide-react'
import { type Claim, scoreToStatus, parseScoreBreakdown, type ScoreBreakdown } from '../../data/types'
import {
  fetchAllClaims, getForensicAuditUrl, copilotChat, fetchCopilotHistory,
  fetchSiuStatus, castSiuVote, moderatorApprove, moderatorReject, markReviewDone,
} from '../../data/api'
import { StatusPill, RiskBadge, SectionHeading, Btn, C } from '../common/ui'
import { ScoreBreakdownPanel } from './ScoreBreakdownPanel'

function apiClaimToLocal(c: any): Claim {
  const score = c.fraud_confidence_score ?? 0
  const findings = c.analyses?.flatMap((a: any) => {
    try { const d = JSON.parse(a.findings_json); return d.findings?.map((f: any) => f.detail) || [] } catch { return [] }
  }) || []
  const created = c.created_at ? new Date(c.created_at) : new Date()
  const diffMin = Math.floor((Date.now() - created.getTime()) / 60000)
  const timeAgo = diffMin < 60 ? `${diffMin}m ago` : `${Math.floor(diffMin / 60)}h ${diffMin % 60}m ago`

  const auditTrail = (c.audit_trail || []).map((e: any) => ({
    time: e.created_at ? new Date(e.created_at).toLocaleTimeString() : '',
    event: (e.action || '').replace(/_/g, ' ').replace(/^./, (ch: string) => ch.toUpperCase()),
  })).reverse()

  const firstDoc = c.documents?.[0]

  let reportSummary, reportRecommendation
  let modalityExplanations: { modality: string; score: number; explanation: string }[] = []
  let scoreBreakdown: ScoreBreakdown | undefined
  try {
    const report = JSON.parse(c.artifact_report)
    reportSummary = report?.summary
    reportRecommendation = report?.recommendation
    modalityExplanations = (report?.modality_reports || []).map((m: any) => ({
      modality: m.modality, score: m.raw_score, explanation: m.explanation || '',
    }))
    scoreBreakdown = parseScoreBreakdown(report)
  } catch { /* no report yet */ }

  return {
    id: c.claim_number,
    name: c.claimant_name || 'Unknown',
    score,
    status: scoreToStatus(score),
    time: timeAgo,
    isLive: c.status === 'processing',
    incidentType: 'Motor Claim',
    location: c.accident_location || '',
    description: c.accident_description || '',
    coverageType: '',
    findings,
    auditTrail,
    hasVideo: !!c.video_url,
    hasAudio: !!c.audio_url,
    hasImage: !!c.image_url,
    hasPdf: !!firstDoc,
    videoUrl: c.video_url || undefined,
    imageUrl: c.image_url || undefined,
    audioUrl: c.audio_url || undefined,
    pdfUrl: firstDoc?.file_url || undefined,
    pdfName: firstDoc?.file_url?.split('/').pop() || undefined,
    backendId: c.id,
    backendStatus: c.status,
    modalities: c.analyses?.length || 0,
    payoutAmountCents: c.payout_amount_cents ?? undefined,
    payoutTransactionId: c.payout_transaction_id ?? undefined,
    claimAmountCents: c.claim_amount_cents ?? undefined,
    reportSummary,
    reportRecommendation,
    modalityExplanations,
    scoreBreakdown,
    inQueue: !!c.in_queue,
    inCaseFiles: !!c.in_case_files,
    queueAction: c.queue_action ?? null,
    decidedBy: c.decided_by ?? null,
    moderatorDecision: c.moderator_decision ?? null,
    rejectionReason: c.rejection_reason ?? undefined,
    policyNumber: c.policy_number ?? undefined,
    policyStatus: c.policy_status ?? undefined,
    coverageLabel: c.coverage_label ?? undefined,
    claimantEmail: c.claimant_email ?? undefined,
    updatedAt: c.updated_at ?? undefined,
  }
}

function useLiveClaims() {
  const [liveClaims, setLiveClaims] = useState<Claim[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let active = true
    const load = async () => {
      const data = await fetchAllClaims()
      if (active && Array.isArray(data)) {
        // Claims Queue = still-pending claims, plus system auto-approved ones
        // pinned first for review-only visibility (see claims.py::_decision_fields).
        // Anything a moderator/SIU quorum has already decided moves to Case Files.
        const queued = data.map(apiClaimToLocal).filter(c => c.inQueue)
        queued.sort((a, b) => (a.queueAction === 'review_only' ? 0 : 1) - (b.queueAction === 'review_only' ? 0 : 1))
        setLiveClaims(queued)
        setLoaded(true)
      }
    }
    load()
    const interval = setInterval(load, 5000)
    return () => { active = false; clearInterval(interval) }
  }, [])

  return { liveClaims, loaded }
}

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
      <StatusPill status={scoreToStatus(score)} size="xs" />
    </div>
  )
}

// ── AI Copilot chat ───────────────────────────────────────────────────────────
const SUGGESTED = [
  'Why was this flagged?',
  'Is the claimed amount reasonable for this damage?',
  "What's the confidence level on the audio analysis?",
  'Summarize the evidence for this claim',
]

interface ChatMsg { from: 'user' | 'ai'; text: string }

function AICopilot({ claim }: { claim: Claim }) {
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState(false)
  const chatContainerRef = useRef<HTMLDivElement>(null)

  // Load prior conversation for this claim
  useEffect(() => {
    let active = true
    fetchCopilotHistory(claim.backendId).then((history: any[]) => {
      if (!active) return
      const loaded: ChatMsg[] = (history || []).map(m => ({
        from: m.role === 'assistant' ? 'ai' : 'user',
        text: m.content,
      }))
      if (loaded.length === 0) {
        loaded.push({ from: 'ai', text: `I've completed multi-modal analysis on ${claim.id}. Ask me anything about the findings, or click a suggested question below.` })
      }
      setMessages(loaded)
      setHistoryLoaded(true)
    })
    return () => { active = false }
  }, [claim.backendId])

  const hasUserMessages = messages.some(m => m.from === 'user')

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight
    }
  }, [messages, typing])

  const ask = async (q: string) => {
    if (!q.trim()) return
    setMessages(m => [...m, { from: 'user', text: q }])
    setInput('')
    setTyping(true)
    try {
      const data = await copilotChat(claim.backendId, q)
      setMessages(m => [...m, { from: 'ai', text: data.content || data.response || 'No response.' }])
    } catch {
      setMessages(m => [...m, { from: 'ai', text: 'Failed to reach the AI copilot. Is the backend running?' }])
    } finally {
      setTyping(false)
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
      </div>
      {/* Suggested chips — only before the first question */}
      {historyLoaded && !hasUserMessages && (
        <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 4, paddingTop: 6, paddingBottom: 6 }}>
          {SUGGESTED.map(q => (
            <button key={q} onClick={() => ask(q)} style={{ fontSize: 10, padding: '3px 8px', borderRadius: 20, background: '#EFF6FF', border: '1px solid #BFDBFE', color: '#2563EB', cursor: 'pointer', fontFamily: 'inherit' }}>
              {q}
            </button>
          ))}
        </div>
      )}
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

// ── SIU Quorum Voting (live) ──────────────────────────────────────────────────
interface Officer { id: number; name: string; role: string }

function SIUVoting({ claim }: { claim: Claim }) {
  const [officers, setOfficers] = useState<Officer[]>([])
  const [siuStatus, setSiuStatus] = useState<any>(null)
  const [notes, setNotes] = useState<Record<number, string>>({})
  const [pendingVote, setPendingVote] = useState<Record<number, 'confirm_fraud' | 'clear' | undefined>>({})
  const [error, setError] = useState('')

  // The panel comes from the backend (officers actually assigned to this claim),
  // not from filtering the full roster by role — that's what previously let the
  // rendered panel be smaller than required_votes, making quorum unreachable.
  const load = async () => {
    const status = await fetchSiuStatus(claim.backendId)
    setSiuStatus(status)
    setOfficers((status?.panel || []).map((p: any) => ({ id: p.officer_id, name: p.name, role: p.role })))
  }

  useEffect(() => { load() }, [claim.backendId])

  const votesCast: any[] = siuStatus?.votes || []

  const submitVote = async (officerId: number) => {
    const vote = pendingVote[officerId]
    if (!vote) return
    setError('')
    try {
      await castSiuVote(claim.backendId, officerId, vote, notes[officerId] || '')
      await load()
    } catch (e: any) {
      setError(e.message)
    }
  }

  if (claim.backendStatus === 'siu_confirmed_fraud' || siuStatus?.review_status === 'confirmed_fraud') {
    return (
      <div style={{ background: '#FFF5F5', border: '1px solid #FECACA', borderRadius: 8, padding: '14px', textAlign: 'center' }}>
        <XCircle size={20} color={C.red} style={{ marginBottom: 6 }} />
        <div style={{ fontSize: 13, fontWeight: 700, color: C.red }}>Fraud Confirmed — Claim Denied</div>
        <div style={{ fontSize: 10, color: C.muted, marginTop: 4 }}>Final vote: {siuStatus?.fraud_votes ?? '–'} Confirm Fraud · {siuStatus?.clear_votes ?? '–'} Clear</div>
      </div>
    )
  }
  if (claim.backendStatus === 'siu_cleared' || siuStatus?.review_status === 'cleared') {
    return (
      <div style={{ background: '#F0FDF4', border: '1px solid #BBF7D0', borderRadius: 8, padding: '14px', textAlign: 'center' }}>
        <CheckCircle size={20} color={C.green} style={{ marginBottom: 6 }} />
        <div style={{ fontSize: 13, fontWeight: 700, color: C.green }}>Claim Cleared — No Fraud Found</div>
        <div style={{ fontSize: 10, color: C.muted, marginTop: 4 }}>Final vote: {siuStatus?.fraud_votes ?? '–'} Confirm Fraud · {siuStatus?.clear_votes ?? '–'} Clear</div>
      </div>
    )
  }

  return (
    <div>
      <div style={{ background: '#FFF5F5', border: `1px solid #FECACA`, borderRadius: 8, padding: '8px 12px', marginBottom: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: C.red }}>SIU Quorum Required</span>
        <span style={{ fontSize: 11, color: C.muted }}>{siuStatus?.votes_cast ?? 0} of {siuStatus?.required_votes ?? officers.length} votes cast</span>
      </div>
      {error && (
        <div style={{ background: '#FFF5F5', border: '1px solid #FECACA', borderRadius: 7, padding: '6px 10px', marginBottom: 8, fontSize: 10, color: C.red }}>{error}</div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {officers.length === 0 && (
          <div style={{ fontSize: 11, color: C.mutedLight, textAlign: 'center', padding: '10px 0' }}>No SIU officers available.</div>
        )}
        {officers.map(o => {
          const cast = votesCast.find(v => v.officer_id === o.id)
          const sel = pendingVote[o.id]
          return (
            <div key={o.id} style={{ border: `1px solid ${C.border}`, borderRadius: 8, padding: '10px 12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: !cast && sel ? 8 : 0 }}>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 600, color: C.text }}>{o.name}</div>
                  <div style={{ fontSize: 9, color: C.mutedLight }}>{o.role === 'senior' ? 'Senior Officer' : o.role === 'moderator' ? 'Moderator' : 'SIU Officer'}</div>
                </div>
                {cast ? (
                  <span style={{ fontSize: 10, fontWeight: 700, padding: '3px 8px', borderRadius: 6, background: cast.vote === 'confirm_fraud' ? '#FFF5F5' : '#F0FDF4', border: `1px solid ${cast.vote === 'confirm_fraud' ? '#FECACA' : '#BBF7D0'}`, color: cast.vote === 'confirm_fraud' ? C.red : C.green }}>
                    {cast.vote === 'confirm_fraud' ? 'Voted: Confirm Fraud' : 'Voted: Clear'}
                  </span>
                ) : (
                  <div style={{ display: 'flex', gap: 4 }}>
                    <button onClick={() => setPendingVote(p => ({ ...p, [o.id]: p[o.id] === 'confirm_fraud' ? undefined : 'confirm_fraud' }))} style={{ fontSize: 10, padding: '3px 8px', borderRadius: 6, border: `1px solid ${sel === 'confirm_fraud' ? C.red : C.border}`, background: sel === 'confirm_fraud' ? '#FFF5F5' : '#fff', color: sel === 'confirm_fraud' ? C.red : C.muted, cursor: 'pointer', fontWeight: sel === 'confirm_fraud' ? 700 : 400 }}>
                      Confirm Fraud
                    </button>
                    <button onClick={() => setPendingVote(p => ({ ...p, [o.id]: p[o.id] === 'clear' ? undefined : 'clear' }))} style={{ fontSize: 10, padding: '3px 8px', borderRadius: 6, border: `1px solid ${sel === 'clear' ? C.green : C.border}`, background: sel === 'clear' ? '#F0FDF4' : '#fff', color: sel === 'clear' ? C.green : C.muted, cursor: 'pointer', fontWeight: sel === 'clear' ? 700 : 400 }}>
                      Clear
                    </button>
                  </div>
                )}
              </div>
              {!cast && sel && (
                <div style={{ display: 'flex', gap: 6 }}>
                  <input
                    value={notes[o.id] || ''} onChange={e => setNotes(n => ({ ...n, [o.id]: e.target.value }))}
                    placeholder="Optional notes…"
                    style={{ flex: 1, boxSizing: 'border-box' as const, fontSize: 10, padding: '5px 8px', borderRadius: 5, border: `1px solid ${C.border}`, background: '#F8FAFC', color: C.text, outline: 'none', fontFamily: 'inherit' }}
                  />
                  <button onClick={() => submitVote(o.id)} style={{ fontSize: 10, fontWeight: 700, padding: '5px 10px', borderRadius: 5, border: 'none', background: C.blue, color: '#fff', cursor: 'pointer' }}>
                    Cast Vote
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Moderator Actions (live) ──────────────────────────────────────────────────
function ReviewDoneAction({ claim }: { claim: Claim }) {
  const [state, setState] = useState<'idle' | 'working' | 'done'>('idle')
  const [error, setError] = useState('')

  const complete = async () => {
    setState('working'); setError('')
    try { await markReviewDone(claim.backendId); setState('done') }
    catch (e: any) { setError(e.message); setState('idle') }
  }

  if (state === 'done') return (
    <div style={{ background: '#F0FDF4', border: '1px solid #BBF7D0', borderRadius: 8, padding: '12px 14px', display: 'flex', gap: 10, alignItems: 'center' }}>
      <CheckCircle size={16} color={C.green} />
      <div>
        <div style={{ fontSize: 12, fontWeight: 700, color: C.text }}>Review recorded</div>
        <div style={{ fontSize: 10, color: C.muted, marginTop: 2 }}>{claim.id} is moving to Case Files.</div>
      </div>
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {error && (
        <div style={{ background: '#FFF5F5', border: '1px solid #FECACA', borderRadius: 7, padding: '6px 10px', fontSize: 10, color: C.red }}>{error}</div>
      )}
      <Btn fullWidth variant="success" onClick={complete} disabled={state === 'working'}>
        <CheckCircle size={13} /> {state === 'working' ? 'Recording…' : 'Review Done'}
      </Btn>
    </div>
  )
}


function ModeratorActions({ claim }: { claim: Claim }) {
  const [state, setState] = useState<'idle' | 'rejecting' | 'working' | 'approved' | 'rejected'>('idle')
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')

  const approve = async () => {
    setState('working'); setError('')
    try { await moderatorApprove(claim.backendId); setState('approved') }
    catch (e: any) { setError(e.message); setState('idle') }
  }

  const reject = async () => {
    setState('working'); setError('')
    try { await moderatorReject(claim.backendId, reason); setState('rejected') }
    catch (e: any) { setError(e.message); setState('rejecting') }
  }

  if (claim.backendStatus === 'rejected' || state === 'rejected') return (
    <div style={{ background: '#FFF5F5', border: '1px solid #FECACA', borderRadius: 8, padding: '14px', display: 'flex', gap: 10, alignItems: 'center' }}>
      <XCircle size={18} color={C.red} />
      <div>
        <div style={{ fontSize: 12, fontWeight: 700, color: C.text }}>Claim Rejected</div>
        {reason && <div style={{ fontSize: 10, color: C.muted, marginTop: 2 }}>Reason: {reason}</div>}
      </div>
    </div>
  )

  if (state === 'approved' || claim.backendStatus === 'auto_approved') return (
    <div style={{ background: '#F0FDF4', border: '1px solid #BBF7D0', borderRadius: 8, padding: '14px', display: 'flex', gap: 10, alignItems: 'center' }}>
      <CheckCircle size={18} color={C.green} />
      <div>
        <div style={{ fontSize: 12, fontWeight: 700, color: C.text }}>Claim Approved</div>
        <div style={{ fontSize: 10, color: C.muted, marginTop: 2 }}>Payout initiated for {claim.id}</div>
      </div>
    </div>
  )

  if (claim.backendStatus !== 'moderator_review') return (
    <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8, padding: '12px', fontSize: 11, color: C.muted, textAlign: 'center' }}>
      No moderator action available — claim status is "{claim.backendStatus.replace(/_/g, ' ')}".
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {error && (
        <div style={{ background: '#FFF5F5', border: '1px solid #FECACA', borderRadius: 7, padding: '6px 10px', fontSize: 10, color: C.red }}>{error}</div>
      )}
      <Btn fullWidth variant="success" onClick={approve} disabled={state === 'working'}>
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
              <Btn variant="danger" size="sm" onClick={reject} style={{ flex: 1 }}>Confirm Rejection</Btn>
            </div>
          </div>
        )
        : <Btn fullWidth variant="danger" onClick={() => setState('rejecting')} disabled={state === 'working'}><XCircle size={13} /> Reject Claim</Btn>
      }
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Main: ClaimsQueue
// ═══════════════════════════════════════════════════════════════════════════════
export default function ClaimsQueue({ headerSearch }: { headerSearch: string }) {
  const { liveClaims: CLAIMS, loaded } = useLiveClaims()
  const [selected, setSelected] = useState('')
  const [filter, setFilter] = useState<'all' | 'high' | 'medium' | 'low'>('all')
  const [search, setSearch] = useState('')
  const [showOverlay, setShowOverlay] = useState(true)
  const [rightSection, setRightSection] = useState<'analysis' | 'copilot' | 'voting'>('analysis')

  const q = headerSearch || search
  const visible = CLAIMS.filter(c => {
    const rm = filter === 'all' || (filter === 'high' && c.score > 85) || (filter === 'medium' && c.score >= 15 && c.score <= 85) || (filter === 'low' && c.score < 15)
    const sm = !q || c.name.toLowerCase().includes(q.toLowerCase()) || c.id.toLowerCase().includes(q.toLowerCase())
    return rm && sm
  })

  const claim = CLAIMS.find(c => c.id === selected) ?? CLAIMS[0]

  // ── Empty state ──
  if (loaded && CLAIMS.length === 0) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: C.bg, gap: 10 }}>
        <div style={{ width: 56, height: 56, borderRadius: 16, background: '#EFF6FF', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Inbox size={24} color={C.blue} />
        </div>
        <div style={{ fontSize: 15, fontWeight: 700, color: C.text }}>No claims yet</div>
        <div style={{ fontSize: 12, color: C.muted, textAlign: 'center', maxWidth: 320, lineHeight: 1.6 }}>
          Claims submitted through the mobile FNOL app will appear here in real time with AI fraud analysis.
        </div>
      </div>
    )
  }

  if (!claim) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: C.bg, gap: 8, color: C.muted, fontSize: 13 }}>
        <Loader size={16} style={{ animation: 'spin-slow 1s linear infinite' }} /> Loading claims…
      </div>
    )
  }

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
            const sel = claim.id === c.id
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
                    {c.queueAction === 'review_only' && <span style={{ fontSize: 8, fontWeight: 700, background: '#F0FDF4', color: C.green, border: '1px solid #BBF7D0', borderRadius: 3, padding: '0 4px' }}>REVIEW ONLY</span>}
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
            <div style={{ fontSize: 10, color: C.mutedLight, fontFamily: 'monospace', marginTop: 1 }}>{claim.id} · {claim.name}</div>
          </div>
          {/* Overlay toggle */}
          <button onClick={() => setShowOverlay(v => !v)} style={{ display: 'flex', alignItems: 'center', gap: 7, background: showOverlay ? '#EFF6FF' : '#fff', border: `1px solid ${showOverlay ? '#BFDBFE' : C.border}`, borderRadius: 7, padding: '5px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, color: showOverlay ? C.blue : C.muted }}>
            {showOverlay ? <Layers size={13} /> : <Eye size={13} />}
            {showOverlay ? 'Heatmap ON' : 'Heatmap OFF'}
          </button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* Video evidence */}
          {claim.videoUrl && (
            <div style={{ borderRadius: 10, overflow: 'hidden', background: '#000', position: 'relative', aspectRatio: '16/9', border: `1px solid ${C.border}` }}>
              <video src={claim.videoUrl} controls style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }} />
              {showOverlay && claim.score > 50 && (
                <div style={{ position: 'absolute', top: 10, left: 10, background: 'rgba(239,68,68,0.88)', borderRadius: 5, padding: '3px 8px', display: 'flex', alignItems: 'center', gap: 4, pointerEvents: 'none' }}>
                  <Layers size={10} color="#fff" />
                  <span style={{ fontSize: 9, color: '#fff', fontFamily: 'monospace' }}>AI VIDEO ANALYSIS</span>
                </div>
              )}
              <div style={{ position: 'absolute', top: 10, right: 10, background: 'rgba(0,0,0,0.55)', borderRadius: 6, padding: '4px 8px', textAlign: 'center', pointerEvents: 'none' }}>
                <div style={{ fontSize: 7, color: 'rgba(255,255,255,0.5)' }}>RISK</div>
                <div style={{ fontSize: 16, fontWeight: 800, color: claim.score > 85 ? C.red : claim.score >= 15 ? C.amber : C.green, fontFamily: 'monospace' }}>{claim.score}%</div>
              </div>
            </div>
          )}

          {/* Image evidence */}
          {claim.imageUrl && (
            <div style={{ borderRadius: 10, overflow: 'hidden', background: '#000', position: 'relative', border: `1px solid ${C.border}` }}>
              <img src={claim.imageUrl} alt="Damage photo evidence" style={{ width: '100%', display: 'block', objectFit: 'contain', maxHeight: 400 }} />
              {showOverlay && claim.score > 50 && (
                <div style={{ position: 'absolute', top: 10, left: 10, background: 'rgba(239,68,68,0.88)', borderRadius: 5, padding: '3px 8px', display: 'flex', alignItems: 'center', gap: 4, pointerEvents: 'none' }}>
                  <Layers size={10} color="#fff" />
                  <span style={{ fontSize: 9, color: '#fff', fontFamily: 'monospace' }}>AI IMAGE ANALYSIS</span>
                </div>
              )}
            </div>
          )}

          {/* Audio player */}
          {claim.audioUrl && (
            <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 8, padding: '12px 14px' }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: 'uppercase' as const, letterSpacing: '0.06em', marginBottom: 8 }}>Voice Statement</div>
              <audio controls style={{ width: '100%', height: 36 }} src={claim.audioUrl}>
                Your browser does not support audio playback.
              </audio>
            </div>
          )}

          {/* Incident details */}
          <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 8, padding: '12px 14px' }}>
            <SectionHeading>Incident Details</SectionHeading>
            <div style={{ fontSize: 11, color: C.textSub, lineHeight: 1.6 }}>
              {claim.location && <div style={{ marginBottom: 4 }}><strong>Location:</strong> {claim.location}</div>}
              {claim.description && <div style={{ marginBottom: claim.claimAmountCents != null ? 4 : 0 }}><strong>Description:</strong> {claim.description}</div>}
              {claim.claimAmountCents != null && (
                <div><strong>Claim Amount:</strong> ${(claim.claimAmountCents / 100).toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
              )}
            </div>
          </div>

          {/* PDF document */}
          {claim.pdfUrl && (
            <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 8, padding: '12px 14px', display: 'flex', gap: 10, alignItems: 'center' }}>
              <FileText size={16} color={C.muted} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: C.text }}>{claim.pdfName}</div>
                <div style={{ fontSize: 9, color: C.mutedLight }}>Supporting document</div>
              </div>
              <a href={claim.pdfUrl} target="_blank" rel="noopener noreferrer" style={{ fontSize: 11, padding: '4px 10px', borderRadius: 6, border: `1px solid ${C.border}`, background: '#fff', color: C.muted, cursor: 'pointer', textDecoration: 'none' }}>View</a>
            </div>
          )}
        </div>
      </div>

      {/* ── RIGHT: Analysis & Actions ──────────────────────────────────────── */}
      <div style={{ background: '#fff', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ padding: '10px 14px', borderBottom: `1px solid ${C.border}`, flexShrink: 0 }}>
          <div style={{ fontSize: 12, fontWeight: 700 }}>AI Analysis</div>
          <div style={{ fontSize: 9, color: C.mutedLight, fontFamily: 'monospace', marginTop: 1 }}>{claim.modalities} signals analyzed · {claim.time}</div>
          {/* Sub-nav */}
          <div style={{ display: 'flex', gap: 2, marginTop: 8 }}>
            {([['analysis', 'Findings'], ['copilot', 'AI Copilot'], ['voting', claim.backendStatus === 'siu_investigation' ? 'SIU Vote' : claim.queueAction === 'review_only' ? 'Details' : 'Actions']] as const).map(([id, label]) => (
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
              </div>

              {/* Per-level score division — shown for every claim, fraud or not */}
              {claim.scoreBreakdown && <ScoreBreakdownPanel breakdown={claim.scoreBreakdown} />}

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
                {claim.auditTrail.length === 0
                  ? <div style={{ fontSize: 11, color: C.mutedLight, padding: '8px 0' }}>No audit events recorded yet.</div>
                  : (
                    <div style={{ border: `1px solid ${C.border}`, borderRadius: 8, overflow: 'hidden' }}>
                      {claim.auditTrail.map((e, i, a) => (
                        <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', padding: '8px 12px', borderBottom: i < a.length - 1 ? `1px solid #F8FAFC` : 'none' }}>
                          <div style={{ width: 6, height: 6, borderRadius: '50%', background: i === 0 ? C.green : C.primary, marginTop: 3, flexShrink: 0 }} />
                          <span style={{ fontSize: 9, color: C.mutedLight, fontFamily: 'monospace', flexShrink: 0 }}>{e.time}</span>
                          <span style={{ fontSize: 10, color: C.textSub, lineHeight: 1.4 }}>{e.event}</span>
                        </div>
                      ))}
                    </div>
                  )
                }
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
              {claim.backendStatus === 'siu_investigation' && <SIUVoting key={claim.id} claim={claim} />}
              {claim.queueAction !== 'review_only' && claim.backendStatus !== 'siu_investigation' && (
                <ModeratorActions key={claim.id} claim={claim} />
              )}
              {claim.queueAction === 'review_only' && (
                <>
                  {/* System auto-approved — visible for review, no action needed or possible */}
                  <div style={{ background: '#F0FDF4', border: '1px solid #BBF7D0', borderRadius: 8, padding: '14px' }}>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                      <CheckCircle size={18} color={C.green} />
                      <div style={{ fontSize: 12, fontWeight: 700, color: C.text }}>Auto-Approved — Payout Complete</div>
                    </div>
                    <div style={{ fontSize: 11, color: C.muted, lineHeight: 1.6 }}>
                      This claim passed AI verification and was paid automatically. No officer action is required — it also appears in Case Files for the permanent record.
                    </div>
                    {claim.payoutAmountCents != null && (
                      <div style={{ marginTop: 10, background: '#fff', border: '1px solid #BBF7D0', borderRadius: 7, padding: '8px 12px' }}>
                        <div style={{ fontSize: 9, color: C.mutedLight, textTransform: 'uppercase' as const, letterSpacing: '0.05em' }}>Payout Amount</div>
                        <div style={{ fontSize: 18, fontWeight: 800, color: C.green }}>${(claim.payoutAmountCents / 100).toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
                        {claim.payoutTransactionId && (
                          <div style={{ fontSize: 9, color: C.mutedLight, fontFamily: 'monospace', marginTop: 3 }}>{claim.payoutTransactionId}</div>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Human-readable AI analysis */}
                  {(claim.reportSummary || claim.modalityExplanations.length > 0) && (
                    <div>
                      <SectionHeading>AI Analysis Report</SectionHeading>
                      {claim.reportSummary && (
                        <div style={{ fontSize: 11, color: C.textSub, lineHeight: 1.6, background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8, padding: '10px 12px', marginBottom: 8 }}>
                          {claim.reportSummary}
                        </div>
                      )}
                      {claim.modalityExplanations.map(m => (
                        <div key={m.modality} style={{ border: `1px solid ${C.border}`, borderRadius: 7, padding: '8px 10px', marginBottom: 6 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                            <span style={{ fontSize: 10, fontWeight: 700, color: C.text, textTransform: 'capitalize' as const }}>{m.modality}</span>
                            <span style={{ fontSize: 10, fontWeight: 700, color: m.score > 85 ? C.red : m.score >= 15 ? C.amber : C.green }}>{Math.round(m.score)}%</span>
                          </div>
                          <div style={{ fontSize: 10, color: C.muted, lineHeight: 1.5 }}>{m.explanation}</div>
                        </div>
                      ))}
                      {claim.reportRecommendation && (
                        <div style={{ fontSize: 10, color: C.textSub, fontStyle: 'italic' as const, marginTop: 4 }}>{claim.reportRecommendation}</div>
                      )}
                    </div>
                  )}

                  {/* Officer acknowledges the review — claim leaves the Queue for Case Files */}
                  <ReviewDoneAction key={claim.id} claim={claim} />
                </>
              )}
              <div style={{ marginTop: 4 }}>
                <a href={getForensicAuditUrl(claim.backendId)} target="_blank" rel="noopener noreferrer" style={{ textDecoration: 'none', display: 'block' }}>
                  <Btn fullWidth variant="outline" size="sm">
                    <FileText size={13} /> Export PDF Forensic Audit Report
                  </Btn>
                </a>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
