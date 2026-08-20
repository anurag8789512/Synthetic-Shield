import { useState, useEffect } from 'react'
import { Download, FileText } from 'lucide-react'
import { StatusPill, C } from '../common/ui'
import { fetchAllClaims, getReportPdfUrl } from '../../data/api'

interface ReportRow {
  id: string
  title: string
  claimId: number
  date: string
  status: string
}

export default function Reports() {
  const [search, setSearch] = useState('')
  const [reports, setReports] = useState<ReportRow[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let active = true
    const load = async () => {
      const data = await fetchAllClaims()
      if (active && Array.isArray(data)) {
        setReports(
          data
            .filter((c: any) => c.fraud_confidence_score != null)
            .map((c: any) => ({
              id: `RPT-${c.claim_number.replace('CLM-', '')}`,
              title: `AI Analysis Report — ${c.claim_number} (${c.claimant_name || 'Unknown'})`,
              claimId: c.id,
              date: c.created_at ? new Date(c.created_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—',
              status: c.status === 'processing' ? 'Draft' : 'Final',
            }))
        )
        setLoaded(true)
      }
    }
    load()
    const interval = setInterval(load, 10000)
    return () => { active = false; clearInterval(interval) }
  }, [])

  const visible = reports.filter(r =>
    !search || r.title.toLowerCase().includes(search.toLowerCase()) || r.id.toLowerCase().includes(search.toLowerCase())
  )

  if (loaded && reports.length === 0) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: C.bg, gap: 10 }}>
        <div style={{ width: 56, height: 56, borderRadius: 16, background: '#EFF6FF', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <FileText size={24} color={C.blue} />
        </div>
        <div style={{ fontSize: 15, fontWeight: 700, color: C.text }}>No reports yet</div>
        <div style={{ fontSize: 12, color: C.muted, textAlign: 'center', maxWidth: 340, lineHeight: 1.6 }}>
          An AI analysis report is generated for every claim once detection completes.
        </div>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 20, background: C.bg }}>
      <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 10, overflow: 'hidden' }}>
        {/* Toolbar */}
        <div style={{ padding: '12px 16px', borderBottom: `1px solid ${C.border}`, display: 'flex', gap: 10, alignItems: 'center' }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: C.text, marginRight: 8 }}>Reports</div>

          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search reports…"
            style={{ height: 32, background: C.bg, border: `1px solid ${C.border}`, borderRadius: 7, fontSize: 12, padding: '0 10px', outline: 'none', fontFamily: 'inherit', color: C.text, width: 220 }}
          />

          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 11, color: C.mutedLight }}>{visible.length} reports</span>
        </div>

        {/* Table header */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 120px 80px 110px', gap: 0, padding: '8px 16px', background: C.bg, borderBottom: `1px solid ${C.border}` }}>
          {['Report Title', 'Date', 'Status', ''].map(h => (
            <div key={h} style={{ fontSize: 10, fontWeight: 700, color: C.mutedLight, textTransform: 'uppercase' as const, letterSpacing: '0.05em' }}>{h}</div>
          ))}
        </div>

        {/* Rows */}
        {visible.map((r, i) => (
          <div key={r.id} style={{ display: 'grid', gridTemplateColumns: '1fr 120px 80px 110px', padding: '12px 16px', borderBottom: i < visible.length - 1 ? `1px solid #F8FAFC` : 'none', alignItems: 'center' }}>
            <div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <FileText size={14} color={C.mutedLight} />
                <div style={{ fontSize: 12, fontWeight: 600, color: C.text }}>{r.title}</div>
              </div>
              <div style={{ fontSize: 9, color: C.mutedLight, fontFamily: 'monospace', marginTop: 2, marginLeft: 22 }}>{r.id}</div>
            </div>
            <div style={{ fontSize: 11, color: C.muted }}>{r.date}</div>
            <div>
              <StatusPill status={r.status.toLowerCase() as any} size="xs" />
            </div>
            <div>
              <a
                href={getReportPdfUrl(r.claimId)}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  display: 'flex', alignItems: 'center', gap: 5,
                  padding: '5px 10px', borderRadius: 6, border: `1px solid ${C.border}`,
                  background: '#fff', color: C.muted, fontSize: 11, cursor: 'pointer', fontFamily: 'inherit',
                  textDecoration: 'none',
                }}
              >
                <Download size={11} /> Download
              </a>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
