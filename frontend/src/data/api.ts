const API_BASE = 'http://localhost:8000'

export async function fetchAllClaims() {
  const res = await fetch(`${API_BASE}/claims/queue/all`)
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
