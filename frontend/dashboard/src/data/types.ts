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
  reportSummary?: string
  reportRecommendation?: string
  modalityExplanations: { modality: string; score: number; explanation: string }[]
}
