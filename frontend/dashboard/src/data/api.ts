const API_BASE = 'http://localhost:8000'

function officerToken() {
  return sessionStorage.getItem('ss_officer_token') || ''
}

function authHeaders(extra?: Record<string, string>) {
  return { ...extra, Authorization: `Bearer ${officerToken()}` }
}

export async function fetchAllClaims() {
  const res = await fetch(`${API_BASE}/claims/queue/all`, { headers: authHeaders() })
  if (!res.ok) return []
  return res.json()
}

export async function logoutOfficer() {
  try {
    await fetch(`${API_BASE}/auth/logout`, { method: 'POST', headers: authHeaders() })
  } catch { /* server session cleanup is best-effort */ }
  sessionStorage.removeItem('ss_officer_token')
  sessionStorage.removeItem('ss_officer_name')
  sessionStorage.removeItem('ss_officer_role')
}

export async function fetchOfficers() {
  const res = await fetch(`${API_BASE}/efficiency/officers`, { headers: authHeaders() })
  if (!res.ok) return []
  return res.json()
}

export async function fetchWorkloadSummary() {
  const res = await fetch(`${API_BASE}/efficiency/workload-summary`, { headers: authHeaders() })
  if (!res.ok) return null
  return res.json()
}

export async function fetchOfficerAssignments(officerId: number) {
  const res = await fetch(`${API_BASE}/efficiency/officer/${officerId}/assignments`, { headers: authHeaders() })
  if (!res.ok) return null
  return res.json()
}

export async function reassignAssignment(assignmentId: number, newOfficerId: number) {
  const res = await fetch(`${API_BASE}/efficiency/assignments/${assignmentId}/reassign`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ new_officer_id: newOfficerId }),
  })
  const data = await res.json().catch(() => null)
  return { ok: res.ok, detail: data?.detail as string | undefined }
}

export async function fetchSiuStatus(claimId: number) {
  const res = await fetch(`${API_BASE}/claims/${claimId}/siu-status`, { headers: authHeaders() })
  if (!res.ok) return null
  return res.json()
}

export async function castSiuVote(claimId: number, officerId: number, vote: 'confirm_fraud' | 'clear', notes: string) {
  const res = await fetch(`${API_BASE}/claims/${claimId}/siu-vote`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ officer_id: officerId, vote, notes }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Vote failed')
  return data
}

export async function moderatorApprove(claimId: number) {
  const res = await fetch(`${API_BASE}/claims/${claimId}/moderator-approve`, { method: 'POST', headers: authHeaders() })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Approve failed')
  return data
}

export async function markReviewDone(claimId: number) {
  const res = await fetch(`${API_BASE}/claims/${claimId}/review-done`, { method: 'POST', headers: authHeaders() })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Could not record review')
  return data
}

export async function moderatorReject(claimId: number, reason: string) {
  const res = await fetch(`${API_BASE}/claims/${claimId}/moderator-reject`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ reason }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Reject failed')
  return data
}

export async function copilotChat(claimId: number, message: string) {
  const res = await fetch(`${API_BASE}/claims/${claimId}/copilot-chat`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ message }),
  })
  if (!res.ok) throw new Error('Copilot request failed')
  return res.json()
}

export async function fetchCopilotHistory(claimId: number) {
  const res = await fetch(`${API_BASE}/claims/${claimId}/copilot-history`, { headers: authHeaders() })
  if (!res.ok) return []
  return res.json()
}

export async function fetchClaimDetail(claimId: number) {
  const res = await fetch(`${API_BASE}/claims/queue/all`, { headers: authHeaders() })
  if (!res.ok) return null
  const claims = await res.json()
  return claims.find((c: any) => c.id === claimId) || null
}

export async function fetchArtifactReport(claimId: number) {
  const res = await fetch(`${API_BASE}/claims/report/${claimId}`, { headers: authHeaders() })
  if (!res.ok) return null
  return res.json()
}

// These build plain <a href> download links, which can't carry an Authorization
// header — the backend accepts the session token as a `token` query param instead.
export function getReportPdfUrl(claimId: number) {
  return `${API_BASE}/claims/report/${claimId}/pdf?token=${encodeURIComponent(officerToken())}`
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
  return `${API_BASE}/downloads/forensic-audit/${claimId}?token=${encodeURIComponent(officerToken())}`
}
