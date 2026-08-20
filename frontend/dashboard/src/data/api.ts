const API_BASE = 'http://localhost:8000'

export async function fetchAllClaims() {
  const res = await fetch(`${API_BASE}/claims/queue/all`)
  if (!res.ok) return []
  return res.json()
}

export async function fetchOfficers() {
  const res = await fetch(`${API_BASE}/efficiency/officers`)
  if (!res.ok) return []
  return res.json()
}

export async function fetchSiuStatus(claimId: number) {
  const res = await fetch(`${API_BASE}/claims/${claimId}/siu-status`)
  if (!res.ok) return null
  return res.json()
}

export async function castSiuVote(claimId: number, officerId: number, vote: 'confirm_fraud' | 'clear', notes: string) {
  const res = await fetch(`${API_BASE}/claims/${claimId}/siu-vote`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ officer_id: officerId, vote, notes }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Vote failed')
  return data
}

export async function moderatorApprove(claimId: number) {
  const res = await fetch(`${API_BASE}/claims/${claimId}/moderator-approve`, { method: 'POST' })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Approve failed')
  return data
}

export async function moderatorReject(claimId: number, reason: string) {
  const res = await fetch(`${API_BASE}/claims/${claimId}/moderator-reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Reject failed')
  return data
}

export async function copilotChat(claimId: number, message: string) {
  const res = await fetch(`${API_BASE}/claims/${claimId}/copilot-chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ officer_id: 1, message }),
  })
  if (!res.ok) throw new Error('Copilot request failed')
  return res.json()
}

export async function fetchCopilotHistory(claimId: number) {
  const res = await fetch(`${API_BASE}/claims/${claimId}/copilot-history`)
  if (!res.ok) return []
  return res.json()
}

export async function fetchClaimDetail(claimId: number) {
  const res = await fetch(`${API_BASE}/claims/queue/all`)
  if (!res.ok) return null
  const claims = await res.json()
  return claims.find((c: any) => c.id === claimId) || null
}

export async function fetchArtifactReport(claimId: number) {
  const res = await fetch(`${API_BASE}/claims/report/${claimId}`)
  if (!res.ok) return null
  return res.json()
}

export function getReportPdfUrl(claimId: number) {
  return `${API_BASE}/claims/report/${claimId}/pdf`
}

export function getDownloadReportUrl(reportId: string, title: string, type: string, date: string, pages: number, status: string) {
  const params = new URLSearchParams({ title, report_type: type, date, pages: String(pages), status })
  return `${API_BASE}/downloads/report/${reportId}?${params}`
}

export function getDownloadCaseUrl(caseId: string, claimId: string, claimant: string, investigator: string, status: string, score: number, opened: string, notes: string) {
  const params = new URLSearchParams({ claim_id: claimId, claimant, investigator, status, score: String(score), opened, notes })
  return `${API_BASE}/downloads/case/${caseId}?${params}`
}

export function getForensicAuditUrl(claimId: number) {
  return `${API_BASE}/downloads/forensic-audit/${claimId}`
}
