import { useState, useEffect } from 'react'
import type { ReactNode } from 'react'
import {
  Search, Calendar, FileText, FolderOpen, Shield, DollarSign,
  AlertCircle, Mail, ChevronDown,
} from 'lucide-react'
import { StatusPill, RiskBadge, SectionHeading, Divider, C } from '../common/ui'
import { fetchAllClaims, getDownloadCaseUrl, getForensicAuditUrl } from '../../data/api'
import { parseScoreBreakdown, type ScoreBreakdown } from '../../data/types'
import { ScoreBreakdownPanel } from './ScoreBreakdownPanel'

interface CaseFile {
  id: string
  claimId: string
  backendId: number
  claimant: string
  claimantEmail: string
  statusKey: 'approved' | 'moderator_approved' | 'rejected' | 'confirmed_fraud' | 'cleared'
  decidedByLabel: string
  score: number
  opened: string
  decidedAt: string
  location: string
  description: string
  policyNumber: string
  policyStatus: string
  coverageLabel: string
  claimAmountCents?: number
  payoutAmountCents?: number
  payoutTransactionId?: string
  rejectionReason?: string
  notes: string
  videoUrl?: string
  imageUrl?: string
  audioUrl?: string
  pdfUrl?: string
  pdfName?: string
  auditTrail: { time: string; event: string }[]
  scoreBreakdown?: ScoreBreakdown
}

const DECIDED_BY_LABEL: Record<string, string> = {
  system: 'AI Auto-Approval',
  moderator: 'Moderator Decision',
  siu_quorum: 'SIU Quorum Decision',
}

function statusKeyOf(status: string, decidedBy: string | null): CaseFile['statusKey'] {
  if (status === 'auto_approved') return decidedBy === 'moderator' ? 'moderator_approved' : 'approved'
  if (status === 'siu_confirmed_fraud') return 'confirmed_fraud'
  if (status === 'siu_cleared') return 'cleared'
  return 'rejected'
}

function fmtDate(iso?: string) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

function fmtMoney(cents?: number) {
  if (cents == null) return '—'
  return `$${(cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2 })}`
}

function claimToCase(c: any): CaseFile {
  let notes = 'No AI summary is available for this claim.'
  let scoreBreakdown: ScoreBreakdown | undefined
  try {
    const report = JSON.parse(c.artifact_report)
    if (report?.summary) notes = report.summary
    scoreBreakdown = parseScoreBreakdown(report)
  } catch { /* keep default */ }

  const firstDoc = c.documents?.[0]
  const auditTrail = (c.audit_trail || []).map((e: any) => ({
    time: e.created_at ? new Date(e.created_at).toLocaleString() : '',
    event: (e.action || '').replace(/_/g, ' ').replace(/^./, (ch: string) => ch.toUpperCase()),
  })).reverse()

  return {
    id: `CASE-${c.claim_number.replace('CLM-', '')}`,
    claimId: c.claim_number,
    backendId: c.id,
    claimant: c.claimant_name || 'Unknown',
    claimantEmail: c.claimant_email || '',
    statusKey: statusKeyOf(c.status, c.decided_by),
    decidedByLabel: DECIDED_BY_LABEL[c.decided_by as string] || 'Pending',
    score: Math.round(c.fraud_confidence_score ?? 0),
    opened: fmtDate(c.created_at),
    decidedAt: fmtDate(c.updated_at),
    location: c.accident_location || '',
    description: c.accident_description || '',
    policyNumber: c.policy_number || 'N/A',
    policyStatus: c.policy_status || 'N/A',
    coverageLabel: c.coverage_label || 'Motor',
    claimAmountCents: c.claim_amount_cents ?? undefined,
    payoutAmountCents: c.payout_amount_cents ?? undefined,
    payoutTransactionId: c.payout_transaction_id ?? undefined,
    rejectionReason: c.rejection_reason ?? undefined,
    notes,
    videoUrl: c.video_url || undefined,
    imageUrl: c.image_url || undefined,
    audioUrl: c.audio_url || undefined,
    pdfUrl: firstDoc?.file_url || undefined,
    pdfName: firstDoc?.file_url?.split('/').pop() || undefined,
    auditTrail,
    scoreBreakdown,
  }
}

const OUTCOME_FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'approved', label: 'Approved' },
  { id: 'rejected', label: 'Rejected' },
  { id: 'siu', label: 'SIU Outcome' },
] as const
type OutcomeFilter = typeof OUTCOME_FILTERS[number]['id']

function matchesOutcome(c: CaseFile, f: OutcomeFilter) {
  if (f === 'all') return true
  if (f === 'approved') return c.statusKey === 'approved' || c.statusKey === 'moderator_approved' || c.statusKey === 'cleared'
  if (f === 'rejected') return c.statusKey === 'rejected'
  return c.statusKey === 'confirmed_fraud' || c.statusKey === 'cleared'
}

function DetailRow({ icon, label, value, mono }: { icon: ReactNode; label: string; value: string; mono?: boolean }) {
  return (
    <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8, padding: '10px 12px', display: 'flex', gap: 10, alignItems: 'center' }}>
      {icon}
      <div>
        <div style={{ fontSize: 9, color: C.mutedLight, textTransform: 'uppercase' as const, letterSpacing: '0.05em' }}>{label}</div>
        <div style={{ fontSize: 12, fontWeight: 600, color: C.text, fontFamily: mono ? 'monospace' : 'inherit', marginTop: 2 }}>{value}</div>
      </div>
    </div>
  )
}

export default function CaseFiles() {
  const [search, setSearch] = useState('')
  const [outcome, setOutcome] = useState<OutcomeFilter>('all')
  const [cases, setCases] = useState<CaseFile[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let active = true
    const load = async () => {
      const data = await fetchAllClaims()
      if (active && Array.isArray(data)) {
        setCases(data.filter((c: any) => c.in_case_files).map(claimToCase))
        setLoaded(true)
      }
    }
    load()
    const interval = setInterval(load, 10000)
    return () => { active = false; clearInterval(interval) }
  }, [])

  const visible = cases.filter(c =>
    matchesOutcome(c, outcome) &&
    (!search ||
      c.claimant.toLowerCase().includes(search.toLowerCase()) ||
      c.id.toLowerCase().includes(search.toLowerCase()) ||
      c.claimId.toLowerCase().includes(search.toLowerCase()))
  )

  if (loaded && cases.length === 0) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: C.bg, gap: 10 }}>
        <div style={{ width: 56, height: 56, borderRadius: 16, background: '#F9EEF1', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <FolderOpen size={24} color={C.blue} />
        </div>
        <div style={{ fontSize: 15, fontWeight: 700, color: C.text }}>No case files yet</div>
        <div style={{ fontSize: 12, color: C.muted, textAlign: 'center', maxWidth: 360, lineHeight: 1.6 }}>
          A claim moves here once it's been decided — auto-approved, approved or rejected by a moderator, or resolved by SIU quorum vote.
        </div>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0, background: C.bg }}>

      {/* List */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: '#fff' }}>
        <div style={{ padding: '14px 16px', borderBottom: `1px solid ${C.border}`, display: 'flex', gap: 10, alignItems: 'center' }}>
          <div style={{ flex: 1, position: 'relative' }}>
            <Search size={13} color={C.mutedLight} style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)' }} />
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search by case ID, claim, or claimant…" style={{ width: '100%', height: 34, background: C.bg, border: `1px solid ${C.border}`, borderRadius: 7, fontSize: 12, padding: '0 10px 0 30px', outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' as const, color: C.text }} />
          </div>
          <span style={{ fontSize: 11, color: C.mutedLight }}>{visible.length} cases</span>
        </div>

        <div style={{ display: 'flex', gap: 4, padding: '10px 16px', borderBottom: `1px solid ${C.border}` }}>
          {OUTCOME_FILTERS.map(f => (
            <button key={f.id} onClick={() => setOutcome(f.id)} style={{ padding: '4px 10px', borderRadius: 6, fontSize: 10, fontWeight: 600, border: `1px solid ${outcome === f.id ? C.blue : C.border}`, background: outcome === f.id ? '#F9EEF1' : '#fff', color: outcome === f.id ? C.blue : C.muted, cursor: 'pointer' }}>
              {f.label}
            </button>
          ))}
        </div>

        {/* Table header */}
        <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr 150px 80px 24px', gap: 0, padding: '8px 16px', borderBottom: `1px solid ${C.border}`, background: C.bg }}>
          {['Case ID', 'Claimant', 'Outcome', 'Score'].map(h => (
            <div key={h} style={{ fontSize: 10, fontWeight: 700, color: C.mutedLight, textTransform: 'uppercase' as const, letterSpacing: '0.05em' }}>{h}</div>
          ))}
        </div>

        <div style={{ flex: 1, overflowY: 'auto' }}>
          {visible.map(c => {
            const sel = selected === c.id
            return (
              <div key={c.id} style={{ borderBottom: `1px solid #FFFFFF` }}>
                <div
                  onClick={() => setSelected(sel ? null : c.id)}
                  style={{
                    display: 'grid', gridTemplateColumns: '120px 1fr 150px 80px 24px',
                    padding: '12px 16px', cursor: 'pointer', alignItems: 'center',
                    background: sel ? '#F9EEF1' : '#fff',
                    transition: 'background 0.1s',
                  }}
                >
                  <div style={{ fontSize: 11, fontFamily: 'monospace', color: sel ? C.blue : C.textSub, fontWeight: sel ? 700 : 400 }}>{c.id}</div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: C.text }}>{c.claimant}</div>
                  <div><StatusPill status={c.statusKey} size="xs" /></div>
                  <div><RiskBadge score={c.score} /></div>
                  <ChevronDown size={14} color={sel ? C.blue : C.mutedLight} style={{ transform: sel ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }} />
                </div>

                {/* Inline detail dropdown — clicking any non-interactive area closes it */}
                {sel && (
                  <div
                    onClick={e => {
                      const target = e.target as HTMLElement
                      if (target.closest('a, button, video, audio, input, select, textarea')) return
                      setSelected(null)
                    }}
                    style={{ background: C.bg, borderTop: `1px solid ${C.border}`, padding: '16px 20px', cursor: 'pointer' }}
                  >
                    <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 10, padding: 16 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
                        <div>
                          <div style={{ fontSize: 12, fontFamily: 'monospace', color: C.muted, marginBottom: 3 }}>{c.id}</div>
                          <div style={{ fontSize: 16, fontWeight: 800, color: C.text }}>{c.claimant}</div>
                          {c.claimantEmail && (
                            <div style={{ fontSize: 10, color: C.mutedLight, display: 'flex', alignItems: 'center', gap: 4, marginTop: 2 }}>
                              <Mail size={10} /> {c.claimantEmail}
                            </div>
                          )}
                        </div>
                        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                          <StatusPill status={c.statusKey} />
                          <RiskBadge score={c.score} />
                        </div>
                      </div>

                      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>

                        {/* Claim details */}
                        <SectionHeading>Claim Details</SectionHeading>
                        <DetailRow icon={<FileText size={13} color={C.muted} />} label="Claim Number" value={c.claimId} mono />
                        <DetailRow icon={<Calendar size={13} color={C.muted} />} label="Submitted" value={c.opened} />
                        <DetailRow icon={<Calendar size={13} color={C.muted} />} label="Decided" value={`${c.decidedAt} · ${c.decidedByLabel}`} />
                        {c.location && <DetailRow icon={<AlertCircle size={13} color={C.muted} />} label="Accident Location" value={c.location} />}
                        {c.description && (
                          <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8, padding: '10px 12px' }}>
                            <div style={{ fontSize: 9, color: C.mutedLight, textTransform: 'uppercase' as const, letterSpacing: '0.05em', marginBottom: 3 }}>Accident Description</div>
                            <div style={{ fontSize: 12, color: C.textSub, lineHeight: 1.5 }}>{c.description}</div>
                          </div>
                        )}

                        <Divider style={{ margin: '4px 0' }} />

                        {/* Policy details */}
                        <SectionHeading>Policy Details</SectionHeading>
                        <DetailRow icon={<Shield size={13} color={C.muted} />} label="Policy Number" value={c.policyNumber} mono />
                        <DetailRow icon={<Shield size={13} color={C.muted} />} label="Coverage" value={c.coverageLabel} />
                        <DetailRow icon={<Shield size={13} color={C.muted} />} label="Policy Status" value={c.policyStatus} />

                        <Divider style={{ margin: '4px 0' }} />

                        {/* Financials */}
                        <SectionHeading>Claim Amount</SectionHeading>
                        <DetailRow icon={<DollarSign size={13} color={C.muted} />} label="Amount Requested" value={fmtMoney(c.claimAmountCents)} />
                        {c.payoutAmountCents != null && (
                          <DetailRow icon={<DollarSign size={13} color={C.green} />} label="Amount Approved / Paid" value={fmtMoney(c.payoutAmountCents)} />
                        )}
                        {c.payoutTransactionId && (
                          <DetailRow icon={<DollarSign size={13} color={C.muted} />} label="Payout Transaction" value={c.payoutTransactionId} mono />
                        )}
                        {c.rejectionReason && (
                          <div style={{ background: '#FFF5F5', border: '1px solid #FECACA', borderRadius: 8, padding: '10px 12px' }}>
                            <div style={{ fontSize: 9, color: C.red, textTransform: 'uppercase' as const, letterSpacing: '0.05em', marginBottom: 3, fontWeight: 700 }}>Rejection Reason</div>
                            <div style={{ fontSize: 12, color: C.textSub, lineHeight: 1.5 }}>{c.rejectionReason}</div>
                          </div>
                        )}

                        <Divider style={{ margin: '4px 0' }} />

                        {/* Evidence */}
                        <SectionHeading>Evidence</SectionHeading>
                        {!c.videoUrl && !c.imageUrl && !c.audioUrl && !c.pdfUrl && (
                          <div style={{ fontSize: 11, color: C.mutedLight }}>No evidence files on record.</div>
                        )}
                        <div style={{ display: 'grid', gridTemplateColumns: c.videoUrl && c.imageUrl ? '1fr 1fr' : '1fr', gap: 10 }}>
                          {c.videoUrl && (
                            <video src={c.videoUrl} controls style={{ width: '100%', borderRadius: 8, border: `1px solid ${C.border}`, background: '#000' }} />
                          )}
                          {c.imageUrl && (
                            <img src={c.imageUrl} alt="Damage evidence" style={{ width: '100%', borderRadius: 8, border: `1px solid ${C.border}`, maxHeight: 240, objectFit: 'contain', background: '#000' }} />
                          )}
                        </div>
                        {c.audioUrl && (
                          <audio src={c.audioUrl} controls style={{ width: '100%' }} />
                        )}
                        {c.pdfUrl && (
                          <a href={c.pdfUrl} target="_blank" rel="noopener noreferrer" style={{ display: 'flex', gap: 8, alignItems: 'center', textDecoration: 'none', background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8, padding: '10px 12px' }}>
                            <FileText size={14} color={C.muted} />
                            <span style={{ fontSize: 11, color: C.text, fontWeight: 600 }}>{c.pdfName || 'Supporting document'}</span>
                          </a>
                        )}

                        <Divider style={{ margin: '4px 0' }} />

                        <div>
                          <SectionHeading>AI Case Summary</SectionHeading>
                          <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8, padding: '12px' }}>
                            <div style={{ fontSize: 12, color: C.textSub, lineHeight: 1.6 }}>{c.notes}</div>
                          </div>
                        </div>

                        {c.scoreBreakdown && <ScoreBreakdownPanel breakdown={c.scoreBreakdown} />}

                        {c.auditTrail.length > 0 && (
                          <div>
                            <SectionHeading>Audit Trail</SectionHeading>
                            <div style={{ border: `1px solid ${C.border}`, borderRadius: 8, overflow: 'hidden' }}>
                              {c.auditTrail.map((e, i, a) => (
                                <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', padding: '8px 12px', borderBottom: i < a.length - 1 ? `1px solid #FFFFFF` : 'none' }}>
                                  <span style={{ fontSize: 9, color: C.mutedLight, fontFamily: 'monospace', flexShrink: 0 }}>{e.time}</span>
                                  <span style={{ fontSize: 10, color: C.textSub, lineHeight: 1.4 }}>{e.event}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                          <a
                            href={getDownloadCaseUrl(c.id, c.claimId, c.claimant, c.decidedByLabel, c.statusKey, c.score, c.opened, c.notes)}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ flex: 1, padding: '9px', borderRadius: 7, border: `1px solid ${C.border}`, background: '#fff', color: C.muted, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', textDecoration: 'none', textAlign: 'center' as const }}
                          >Export Case Summary</a>
                          <a
                            href={getForensicAuditUrl(c.backendId)}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ flex: 1, padding: '9px', borderRadius: 7, border: `1px solid ${C.border}`, background: '#fff', color: C.muted, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', textDecoration: 'none', textAlign: 'center' as const }}
                          >Full Forensic Audit PDF</a>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
