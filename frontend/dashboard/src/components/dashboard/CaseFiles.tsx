import { useState, useEffect } from 'react'
import { Search, X, User, Calendar, FileText, FolderOpen } from 'lucide-react'
import { StatusPill, RiskBadge, SectionHeading, Divider, C } from '../common/ui'
import { fetchAllClaims, getDownloadCaseUrl } from '../../data/api'

interface CaseFile {
  id: string
  claimId: string
  claimant: string
  investigator: string
  status: string
  score: number
  opened: string
  notes: string
}

const SIU_STATUSES = ['siu_investigation', 'siu_confirmed_fraud', 'siu_cleared']

function claimToCase(c: any): CaseFile {
  let notes = 'Flagged for SIU investigation by AI detection pipeline.'
  try {
    const report = JSON.parse(c.artifact_report)
    if (report?.summary) notes = report.summary
  } catch { /* keep default */ }

  const status = c.status === 'siu_investigation' ? 'open' : c.status === 'siu_confirmed_fraud' ? 'closed' : 'closed'

  return {
    id: `CASE-${c.claim_number.replace('CLM-', '')}`,
    claimId: c.claim_number,
    claimant: c.claimant_name || 'Unknown',
    investigator: 'SIU Quorum',
    status,
    score: Math.round(c.fraud_confidence_score ?? 0),
    opened: c.created_at ? new Date(c.created_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—',
    notes,
  }
}

export default function CaseFiles() {
  const [search, setSearch] = useState('')
  const [cases, setCases] = useState<CaseFile[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let active = true
    const load = async () => {
      const data = await fetchAllClaims()
      if (active && Array.isArray(data)) {
        setCases(data.filter((c: any) => SIU_STATUSES.includes(c.status)).map(claimToCase))
        setLoaded(true)
      }
    }
    load()
    const interval = setInterval(load, 10000)
    return () => { active = false; clearInterval(interval) }
  }, [])

  const visible = cases.filter(c =>
    !search ||
    c.claimant.toLowerCase().includes(search.toLowerCase()) ||
    c.id.toLowerCase().includes(search.toLowerCase()) ||
    c.claimId.toLowerCase().includes(search.toLowerCase())
  )

  const detail = cases.find(c => c.id === selected) ?? (selected === null ? cases[0] : undefined)

  if (loaded && cases.length === 0) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: C.bg, gap: 10 }}>
        <div style={{ width: 56, height: 56, borderRadius: 16, background: '#EFF6FF', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <FolderOpen size={24} color={C.blue} />
        </div>
        <div style={{ fontSize: 15, fontWeight: 700, color: C.text }}>No case files yet</div>
        <div style={{ fontSize: 12, color: C.muted, textAlign: 'center', maxWidth: 340, lineHeight: 1.6 }}>
          A case file opens automatically when a claim is flagged for SIU investigation (fraud score &gt; 85%).
        </div>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 380px', overflow: 'hidden', minHeight: 0, background: C.bg }}>

      {/* List */}
      <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', background: '#fff', borderRight: `1px solid ${C.border}` }}>
        <div style={{ padding: '14px 16px', borderBottom: `1px solid ${C.border}`, display: 'flex', gap: 10, alignItems: 'center' }}>
          <div style={{ flex: 1, position: 'relative' }}>
            <Search size={13} color={C.mutedLight} style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)' }} />
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search by case ID, claim, or claimant…" style={{ width: '100%', height: 34, background: C.bg, border: `1px solid ${C.border}`, borderRadius: 7, fontSize: 12, padding: '0 10px 0 30px', outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' as const, color: C.text }} />
          </div>
          <span style={{ fontSize: 11, color: C.mutedLight }}>{visible.length} cases</span>
        </div>

        {/* Table header */}
        <div style={{ display: 'grid', gridTemplateColumns: '130px 1fr 110px 90px 80px', gap: 0, padding: '8px 16px', borderBottom: `1px solid ${C.border}`, background: C.bg }}>
          {['Case ID', 'Claimant', 'Investigator', 'Status', 'Score'].map(h => (
            <div key={h} style={{ fontSize: 10, fontWeight: 700, color: C.mutedLight, textTransform: 'uppercase' as const, letterSpacing: '0.05em' }}>{h}</div>
          ))}
        </div>

        <div style={{ flex: 1, overflowY: 'auto' }}>
          {visible.map(c => {
            const sel = detail?.id === c.id
            return (
              <div
                key={c.id}
                onClick={() => setSelected(c.id)}
                style={{
                  display: 'grid', gridTemplateColumns: '130px 1fr 110px 90px 80px',
                  padding: '12px 16px', cursor: 'pointer', alignItems: 'center',
                  borderBottom: `1px solid #F8FAFC`,
                  background: sel ? '#EFF6FF' : '#fff',
                  transition: 'background 0.1s',
                }}
              >
                <div style={{ fontSize: 11, fontFamily: 'monospace', color: sel ? C.blue : C.textSub, fontWeight: sel ? 700 : 400 }}>{c.id}</div>
                <div style={{ fontSize: 12, fontWeight: 600, color: C.text }}>{c.claimant}</div>
                <div style={{ fontSize: 11, color: C.muted }}>{c.investigator}</div>
                <div><StatusPill status={c.status as any} size="xs" /></div>
                <div><RiskBadge score={c.score} /></div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Detail panel */}
      <div style={{ background: '#fff', borderLeft: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {detail ? (
          <>
            <div style={{ padding: '14px 16px', borderBottom: `1px solid ${C.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <div style={{ fontSize: 12, fontFamily: 'monospace', color: C.muted, marginBottom: 3 }}>{detail.id}</div>
                <div style={{ fontSize: 16, fontWeight: 800, color: C.text }}>{detail.claimant}</div>
              </div>
              <button onClick={() => setSelected('')} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}><X size={16} color={C.mutedLight} /></button>
            </div>

            <div style={{ flex: 1, overflowY: 'auto', padding: '16px' }}>
              {/* Status + score */}
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 16 }}>
                <StatusPill status={detail.status as any} />
                <RiskBadge score={detail.score} />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {[
                  { icon: <User size={13} color={C.muted} />, label: 'Assigned To', value: detail.investigator },
                  { icon: <FileText size={13} color={C.muted} />, label: 'Related Claim', value: detail.claimId },
                  { icon: <Calendar size={13} color={C.muted} />, label: 'Date Opened', value: detail.opened },
                ].map(row => (
                  <div key={row.label} style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8, padding: '10px 12px', display: 'flex', gap: 10, alignItems: 'center' }}>
                    {row.icon}
                    <div>
                      <div style={{ fontSize: 9, color: C.mutedLight, textTransform: 'uppercase' as const, letterSpacing: '0.05em' }}>{row.label}</div>
                      <div style={{ fontSize: 12, fontWeight: 600, color: C.text, fontFamily: row.label === 'Related Claim' ? 'monospace' : 'inherit', marginTop: 2 }}>{row.value}</div>
                    </div>
                  </div>
                ))}

                <Divider />

                <div>
                  <SectionHeading>AI Case Summary</SectionHeading>
                  <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8, padding: '12px' }}>
                    <div style={{ fontSize: 12, color: C.textSub, lineHeight: 1.6 }}>{detail.notes}</div>
                  </div>
                </div>

                <a
                  href={getDownloadCaseUrl(detail.id, detail.claimId, detail.claimant, detail.investigator, detail.status, detail.score, detail.opened, detail.notes)}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ padding: '9px', borderRadius: 7, border: `1px solid ${C.border}`, background: '#fff', color: C.muted, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', textDecoration: 'none', textAlign: 'center' as const }}
                >Export Report</a>
              </div>
            </div>
          </>
        ) : (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: C.mutedLight, fontSize: 13 }}>
            Select a case to view details
          </div>
        )}
      </div>
    </div>
  )
}
