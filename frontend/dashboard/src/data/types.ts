// Claim status logic (spec §5)
// score < 15  → Auto-Approved · 15-85 → Moderator Review · > 85 → SIU Investigation

export type ClaimStatus = 'approved' | 'review' | 'siu'

export function scoreToStatus(score: number): ClaimStatus {
  if (score < 15) return 'approved'
  if (score <= 85) return 'review'
  return 'siu'
}

export interface AuditEntry {
  time: string
  event: string
}

// Fraud fusion scoring division (parsed from artifact_report.score_breakdown)
export interface ScoreSignal {
  name: string
  value: number | null
  status: 'ok' | 'unavailable' | 'not_applicable'
  weight?: number
  provider?: string
  components?: Record<string, number>
  findings: string[]
}

export interface ScoreBreakdown {
  baseScore: number
  finalScore: number
  escalated: boolean
  escalationSource?: string | null
  routingBand: string
  forcedReviewReason?: string | null
  configVersion?: string
  signals: ScoreSignal[]
}

export function parseScoreBreakdown(report: any): ScoreBreakdown | undefined {
  const sb = report?.score_breakdown
  if (!sb || !Array.isArray(sb.subscores)) return undefined
  const weights = sb.weights_used || {}
  return {
    baseScore: sb.base_score ?? 0,
    finalScore: sb.final_score ?? 0,
    escalated: !!sb.escalated,
    escalationSource: sb.escalation_source ?? null,
    routingBand: sb.routing_band ?? '',
    forcedReviewReason: sb.forced_review_reason ?? null,
    configVersion: sb.config_version,
    signals: sb.subscores.map((s: any) => ({
      name: s.name,
      value: s.value ?? null,
      status: s.status ?? 'ok',
      weight: weights[s.name],
      provider: s.provider,
      components: s.components && Object.keys(s.components).length ? s.components : undefined,
      findings: (s.findings || []).map((f: any) => f.human_readable).filter(Boolean),
    })),
  }
}

export interface Claim {
  id: string
  name: string
  score: number
  status: ClaimStatus
  time: string
  isLive: boolean
  incidentType: string
  location: string
  description: string
  coverageType: string
  findings: string[]
  auditTrail: AuditEntry[]
  hasVideo: boolean
  hasAudio: boolean
  hasImage: boolean
  hasPdf: boolean
  videoUrl?: string
  imageUrl?: string
  audioUrl?: string
  pdfUrl?: string
  pdfName?: string
  backendId: number
  backendStatus: string
  modalities: number
  payoutAmountCents?: number
  payoutTransactionId?: string
  claimAmountCents?: number
  reportSummary?: string
  reportRecommendation?: string
  modalityExplanations: { modality: string; score: number; explanation: string }[]
  scoreBreakdown?: ScoreBreakdown

  // Queue vs. Case Files routing (computed server-side — see claims.py::_decision_fields)
  inQueue: boolean
  inCaseFiles: boolean
  queueAction: 'processing' | 'moderate' | 'siu_vote' | 'review_only' | null
  decidedBy: 'system' | 'moderator' | 'siu_quorum' | null
  moderatorDecision: 'approved' | 'rejected' | null
  rejectionReason?: string
  policyNumber?: string
  policyStatus?: string
  coverageLabel?: string
  claimantEmail?: string
  updatedAt?: string
}
