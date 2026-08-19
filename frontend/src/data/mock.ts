// ── Claim status logic (spec §5) ─────────────────────────────────────────────
// score < 15  → Auto-Approved
// score 15-85 → Moderator Review
// score > 85  → SIU Investigation

export type ClaimStatus = 'approved' | 'review' | 'siu'

export function scoreToStatus(score: number): ClaimStatus {
  if (score < 15) return 'approved'
  if (score <= 85) return 'review'
  return 'siu'
}

export interface AuditEntry { time: string; event: string }

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
  hasPhotos: boolean
  hasPdf: boolean
  fraudAmount: number
}

export const CLAIMS: Claim[] = [
  {
    id: 'CLM-2026-00042', name: 'Marcus J. Webb', score: 94, status: 'siu',
    time: '12m ago', isLive: true, incidentType: 'Auto Collision',
    location: '47 Harbour Bridge Rd, Sydney NSW',
    description: 'Rear-ended at traffic light. Significant bumper and tail-light damage.',
    coverageType: 'Own Damage',
    findings: [
      'Inconsistent specular reflections on bumper region — diffusion model artifacts detected',
      'Voice frequency anomalies detected between 0:02 and 0:05 — voice clone probability 96%',
      'EXIF metadata absent — image fingerprint matches Stable Diffusion v2.1 pipeline',
      'Frame-level GAN artifacts detected at 0:11–0:14 of submitted video',
    ],
    auditTrail: [
      { time: '08:18:04', event: 'AI analysis completed — SIU Investigation triggered' },
      { time: '08:17:52', event: 'EXIF metadata extraction attempted — fields absent' },
      { time: '08:17:31', event: 'Voice biometric scan initiated' },
      { time: '08:17:12', event: 'Frame-level diffusion analysis started' },
      { time: '08:17:01', event: 'Claim CLM-2026-00042 received' },
    ],
    hasVideo: true, hasAudio: true, hasPhotos: true, hasPdf: false, fraudAmount: 14200,
  },
  {
    id: 'CLM-2026-00041', name: 'Adrienne Holloway', score: 67, status: 'review',
    time: '38m ago', isLive: true, incidentType: 'Auto Collision',
    location: '12 George St, Brisbane QLD',
    description: 'Side-swipe on highway. Driver side door and mirror damage.',
    coverageType: 'Comprehensive',
    findings: [
      'Moderate audio frequency variance detected at 0:04–0:06 — low-confidence signal',
      'Minor lighting inconsistency in rear panel region — inconclusive',
    ],
    auditTrail: [
      { time: '07:55:22', event: 'AI analysis completed — Moderator Review triggered' },
      { time: '07:55:10', event: 'Voice biometric scan completed' },
      { time: '07:54:58', event: 'Frame analysis completed' },
      { time: '07:54:31', event: 'Claim CLM-2026-00041 received' },
    ],
    hasVideo: true, hasAudio: true, hasPhotos: true, hasPdf: true, fraudAmount: 6800,
  },
  {
    id: 'CLM-2026-00040', name: 'Priya Subramaniam', score: 73, status: 'review',
    time: '1h 12m ago', isLive: false, incidentType: 'Parking Incident',
    location: '88 Swanston St, Melbourne VIC',
    description: 'Returned to vehicle to find multiple scratches along the passenger side.',
    coverageType: 'Own Damage',
    findings: [
      'Slight audio tone variation at 0:08 — likely road noise interference, low confidence',
    ],
    auditTrail: [
      { time: '07:10:44', event: 'AI analysis completed — Moderator Review triggered' },
      { time: '07:10:30', event: 'Media scan completed' },
      { time: '07:09:55', event: 'Claim CLM-2026-00040 received' },
    ],
    hasVideo: false, hasAudio: true, hasPhotos: true, hasPdf: false, fraudAmount: 3200,
  },
  {
    id: 'CLM-2026-00039', name: 'David Kwan', score: 8, status: 'approved',
    time: '2h 4m ago', isLive: false, incidentType: 'Auto Collision',
    location: '3 Flinders Lane, Melbourne VIC',
    description: 'Minor collision at intersection. Front bumper dented, no injuries.',
    coverageType: 'Third-Party Liability',
    findings: [],
    auditTrail: [
      { time: '06:28:17', event: 'AI analysis completed — Auto-Approved' },
      { time: '06:28:05', event: 'Media scan completed — no anomalies detected' },
      { time: '06:27:41', event: 'Claim CLM-2026-00039 received' },
    ],
    hasVideo: true, hasAudio: true, hasPhotos: true, hasPdf: true, fraudAmount: 1900,
  },
  {
    id: 'CLM-2026-00038', name: 'Fatimah Al-Rashidi', score: 55, status: 'review',
    time: '3h 47m ago', isLive: false, incidentType: 'Hit & Run',
    location: '221 King William St, Adelaide SA',
    description: 'Vehicle hit while parked outside office. Unknown third party fled scene.',
    coverageType: 'Own Damage',
    findings: [
      'Slight metadata timestamp mismatch — GPS time vs. file creation time offset by 4h',
    ],
    auditTrail: [
      { time: '04:35:11', event: 'AI analysis completed — Moderator Review triggered' },
      { time: '04:35:00', event: 'Media scan completed' },
      { time: '04:34:22', event: 'Claim CLM-2026-00038 received' },
    ],
    hasVideo: false, hasAudio: true, hasPhotos: true, hasPdf: false, fraudAmount: 4500,
  },
  {
    id: 'CLM-2026-00037', name: 'Gregory Saunders', score: 42, status: 'review',
    time: '5h 10m ago', isLive: false, incidentType: 'Multi-Vehicle',
    location: 'Pacific Highway, Coffs Harbour NSW',
    description: 'Three-car pile-up on highway exit ramp. Rear and front-end damage.',
    coverageType: 'Comprehensive',
    findings: [
      'Low-confidence audio anomaly — background noise pattern analysis inconclusive',
    ],
    auditTrail: [
      { time: '03:02:55', event: 'AI analysis completed — Moderator Review triggered' },
      { time: '03:02:40', event: 'Media scan completed' },
      { time: '03:01:58', event: 'Claim CLM-2026-00037 received' },
    ],
    hasVideo: true, hasAudio: true, hasPhotos: false, hasPdf: true, fraudAmount: 8700,
  },
]

// ── Policy (FNOL app) ─────────────────────────────────────────────────────────
export const POLICY = {
  holderName: 'Sarah Mitchell',
  policyNumber: 'POL-2026-AU-087234',
  status: 'active' as const,
  vehicle: { make: 'Toyota', model: 'Camry', year: 2023, plate: 'NSW-ABC-1234' },
  coverages: [
    { name: 'Own Damage',                  description: 'Covers repair or replacement costs for your vehicle' },
    { name: 'Third-Party Liability',        description: 'Covers damage or injury caused to third parties' },
    { name: 'Roadside Assistance Add-On',  description: '24/7 breakdown and emergency roadside support' },
  ],
  renewalDate: '15 March 2027',
  premium: '$142.50 / month',
}

// ── Case files ────────────────────────────────────────────────────────────────
export const CASE_FILES = [
  { id: 'CASE-2026-0018', claimId: 'CLM-2026-00042', claimant: 'Marcus J. Webb',    investigator: 'D. Torres',   status: 'open',    score: 94, opened: '24 Jul 2026', notes: 'Diffusion artifacts confirmed by forensic review. Awaiting quorum vote.' },
  { id: 'CASE-2026-0017', claimId: 'CLM-2026-00031', claimant: 'Elena Vasquez',     investigator: 'R. Park',     status: 'open',    score: 91, opened: '21 Jul 2026', notes: 'Voice clone pattern matches known synthetic voice generator.' },
  { id: 'CASE-2026-0016', claimId: 'CLM-2026-00028', claimant: 'Jordan Lee',        investigator: 'D. Torres',   status: 'closed',  score: 88, opened: '18 Jul 2026', notes: 'Confirmed fraud. Claim denied. Case referred to local authorities.' },
  { id: 'CASE-2026-0015', claimId: 'CLM-2026-00019', claimant: 'Nadia Patel',       investigator: 'S. Okonkwo', status: 'open',    score: 96, opened: '15 Jul 2026', notes: 'Highest confidence synthetic score this quarter. Multi-signal confirmation.' },
  { id: 'CASE-2026-0014', claimId: 'CLM-2026-00014', claimant: 'Thomas Brennan',    investigator: 'R. Park',     status: 'closed',  score: 89, opened: '10 Jul 2026', notes: 'Closed — payout blocked. Referred to police.' },
  { id: 'CASE-2026-0013', claimId: 'CLM-2026-00009', claimant: 'Yasmine Bouchard',  investigator: 'S. Okonkwo', status: 'pending', score: 87, opened: '7 Jul 2026',  notes: 'Pending additional evidence from claimant.' },
]

// ── Reports ───────────────────────────────────────────────────────────────────
export const REPORTS = [
  { id: 'RPT-2026-0042', title: 'July 2026 Fraud Pattern Analysis',       type: 'Fraud Pattern Analysis',   date: '24 Jul 2026', status: 'Final', pages: 18 },
  { id: 'RPT-2026-0041', title: 'Weekly SIU Investigation Summary W29',   type: 'Investigation Summary',     date: '21 Jul 2026', status: 'Final', pages: 9 },
  { id: 'RPT-2026-0040', title: 'Q2 2026 Monthly Digest',                  type: 'Monthly Digest',            date: '15 Jul 2026', status: 'Final', pages: 24 },
  { id: 'RPT-2026-0039', title: 'Voice Clone Detection Deep Dive',         type: 'Fraud Pattern Analysis',   date: '10 Jul 2026', status: 'Draft', pages: 12 },
  { id: 'RPT-2026-0038', title: 'June 2026 Monthly Digest',                type: 'Monthly Digest',            date: '30 Jun 2026', status: 'Final', pages: 22 },
  { id: 'RPT-2026-0037', title: 'Deepfake Detection Accuracy Report',      type: 'Investigation Summary',     date: '25 Jun 2026', status: 'Final', pages: 14 },
  { id: 'RPT-2026-0036', title: 'May 2026 Monthly Digest',                 type: 'Monthly Digest',            date: '31 May 2026', status: 'Final', pages: 20 },
]

// ── Analytics ─────────────────────────────────────────────────────────────────
export const VOLUME_TREND = [
  { date: 'Jul 11', total: 42, flagged: 7  },
  { date: 'Jul 12', total: 38, flagged: 5  },
  { date: 'Jul 13', total: 51, flagged: 9  },
  { date: 'Jul 14', total: 45, flagged: 8  },
  { date: 'Jul 15', total: 60, flagged: 12 },
  { date: 'Jul 16', total: 55, flagged: 11 },
  { date: 'Jul 17', total: 48, flagged: 6  },
  { date: 'Jul 18', total: 63, flagged: 14 },
  { date: 'Jul 19', total: 71, flagged: 18 },
  { date: 'Jul 20', total: 58, flagged: 10 },
  { date: 'Jul 21', total: 66, flagged: 15 },
  { date: 'Jul 22', total: 74, flagged: 19 },
  { date: 'Jul 23', total: 69, flagged: 16 },
  { date: 'Jul 24', total: 52, flagged: 13 },
]

export const OUTCOME_DIST = [
  { name: 'Auto-Approved',      value: 162, color: '#10B981' },
  { name: 'Manual Review',      value: 67,  color: '#F59E0B' },
  { name: 'SIU Investigation',  value: 18,  color: '#EF4444' },
]

export const SIGNAL_BREAKDOWN = [
  { type: 'Video Deepfake',     count: 24 },
  { type: 'Voice Clone',        count: 19 },
  { type: 'Photo Manipulation', count: 15 },
  { type: 'Document Forgery',   count: 9  },
]

// ── AI Copilot Q&A map ────────────────────────────────────────────────────────
export const AI_QA: Record<string, string> = {
  'why was this flagged': 'This claim triggered on three converging signals: (1) pixel-level diffusion artifacts on the bumper consistent with Stable Diffusion v2.1; (2) synthetic frequency gaps in the voice statement at 0:03–0:07; and (3) complete absence of EXIF metadata — all authentic smartphone captures retain this.',
  'show audio analysis': 'Voice biometric analysis detected synthetic frequency artifacts at 0:03–0:07. The spectral signature matches a TTS voice-clone pattern. Pitch variance falls outside the natural human distribution at 3.2σ. Confidence: 96%.',
  'compare to similar claims': 'In the past 90 days, 14 claims with similar tri-signal profiles were filed. 12 were confirmed fraud post-SIU. Common pattern: AI-generated bumper damage imagery paired with cloned voice statements submitted within 2 hours of a real incident report from another policyholder.',
  'what evidence is most suspicious': 'The EXIF absence is the strongest single signal — authentic smartphone images always carry camera model, GPS, and timestamp fields. Combined with the diffusion-model pixel fingerprint, this claim scores in the top 5% of synthetic confidence levels seen this year.',
  default: "I've completed multi-modal analysis on this claim. The primary concern is the confluence of visual, audio, and metadata signals. Ask me anything about the specific findings or how this compares to previous cases.",
}
