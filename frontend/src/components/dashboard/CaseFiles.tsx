import { useState } from 'react'
import { Search, X, User, Calendar, FileText } from 'lucide-react'
import { CASE_FILES } from '../../data/mock'
import { StatusPill, RiskBadge, SectionHeading, Divider, C } from '../common/ui'
import { getDownloadCaseUrl } from '../../data/api'

export default function CaseFiles() {
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<string | null>(CASE_FILES[0].id)

  const visible = CASE_FILES.filter(c =>
    !search ||
    c.claimant.toLowerCase().includes(search.toLowerCase()) ||
    c.id.toLowerCase().includes(search.toLowerCase()) ||
    c.investigator.toLowerCase().includes(search.toLowerCase())
  )

  const detail = CASE_FILES.find(c => c.id === selected)

  return (
    <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 380px', overflow: 'hidden', minHeight: 0, background: C.bg }}>

      {/* List */}
      <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', background: '#fff', borderRight: `1px solid ${C.border}` }}>
        <div style={{ padding: '14px 16px', borderBottom: `1px solid ${C.border}`, display: 'flex', gap: 10, alignItems: 'center' }}>
          <div style={{ flex: 1, position: 'relative' }}>
            <Search size={13} color={C.mutedLight} style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)' }} />
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search by case ID, claimant, or investigator…" style={{ width: '100%', height: 34, background: C.bg, border: `1px solid ${C.border}`, borderRadius: 7, fontSize: 12, padding: '0 10px 0 30px', outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' as const, color: C.text }} />
          </div>
          <span style={{ fontSize: 11, color: C.mutedLight }}>{visible.length} cases</span>
        </div>

        {/* Table header */}
        <div style={{ display: 'grid', gridTemplateColumns: '110px 1fr 110px 90px 80px', gap: 0, padding: '8px 16px', borderBottom: `1px solid ${C.border}`, background: C.bg }}>
          {['Case ID', 'Claimant', 'Investigator', 'Status', 'Score'].map(h => (
            <div key={h} style={{ fontSize: 10, fontWeight: 700, color: C.mutedLight, textTransform: 'uppercase' as const, letterSpacing: '0.05em' }}>{h}</div>
          ))}
        </div>

        <div style={{ flex: 1, overflowY: 'auto' }}>
          {visible.map(c => {
            const sel = selected === c.id
            return (
              <div
                key={c.id}
                onClick={() => setSelected(c.id)}
                style={{
                  display: 'grid', gridTemplateColumns: '110px 1fr 110px 90px 80px',
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
              <button onClick={() => setSelected(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}><X size={16} color={C.mutedLight} /></button>
            </div>

            <div style={{ flex: 1, overflowY: 'auto', padding: '16px' }}>
              {/* Status + score */}
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 16 }}>
                <StatusPill status={detail.status as any} />
                <RiskBadge score={detail.score} />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {[
                  { icon: <User size={13} color={C.muted} />, label: 'Assigned Investigator', value: detail.investigator },
                  { icon: <FileText size={13} color={C.muted} />, label: 'Related Claim',      value: detail.claimId },
                  { icon: <Calendar size={13} color={C.muted} />, label: 'Date Opened',        value: detail.opened },
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
                  <SectionHeading>Investigator Notes</SectionHeading>
                  <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8, padding: '12px' }}>
                    <div style={{ fontSize: 12, color: C.textSub, lineHeight: 1.6 }}>{detail.notes}</div>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: 8 }}>
                  <a
                    href={getDownloadCaseUrl(detail.id, detail.claimId, detail.claimant, detail.investigator, detail.status, detail.score, detail.opened, detail.notes)}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ flex: 1, padding: '9px', borderRadius: 7, border: `1px solid ${C.border}`, background: '#fff', color: C.muted, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', textDecoration: 'none', textAlign: 'center' as const }}
                  >Export Report</a>
                  <button style={{ flex: 1, padding: '9px', borderRadius: 7, border: 'none', background: C.blue, color: '#fff', fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>View Claim</button>
                </div>
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
