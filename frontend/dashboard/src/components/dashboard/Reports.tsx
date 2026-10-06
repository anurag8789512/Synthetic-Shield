import { useState, useEffect } from 'react'
import { Download, FileText, ChevronDown } from 'lucide-react'
import { StatusPill, SectionHeading, C } from '../common/ui'
import { fetchAllClaims, getReportPdfUrl } from '../../data/api'
import { serverDate } from '../../data/time'
import { parseScoreBreakdown, type ScoreBreakdown } from '../../data/types'
import { ScoreBreakdownPanel } from './ScoreBreakdownPanel'

interface ReportRow {
  id: string
  title: string
  claimId: number
  claimNumber: string
  claimant: string
  date: string
  status: string
  score: number
  summary?: string
  recommendation?: string
  modalityExplanations: { modality: string; score: number; explanation: string }[]
  scoreBreakdown?: ScoreBreakdown
}

export default function Reports() {
  const [search, setSearch] = useState('')
  const [reports, setReports] = useState<ReportRow[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let active = true
    const load = async () => {
      const data = await fetchAllClaims()
      if (active && Array.isArray(data)) {
        setReports(
          data
            .filter((c: any) => c.fraud_confidence_score != null)
            .map((c: any) => {
              let summary, recommendation
              let modalityExplanations: ReportRow['modalityExplanations'] = []
              let scoreBreakdown: ScoreBreakdown | undefined
              try {
                const report = JSON.parse(c.artifact_report)
                summary = report?.summary
                recommendation = report?.recommendation
                modalityExplanations = (report?.modality_reports || []).map((m: any) => ({
                  modality: m.modality, score: m.raw_score, explanation: m.explanation || '',
                }))
                scoreBreakdown = parseScoreBreakdown(report)
              } catch { /* no report yet */ }

              return {
                id: `RPT-${c.claim_number.replace('CLM-', '')}`,
                title: `AI Analysis Report — ${c.claim_number} (${c.claimant_name || 'Unknown'})`,
                claimId: c.id,
                claimNumber: c.claim_number,
                claimant: c.claimant_name || 'Unknown',
                date: c.created_at ? serverDate(c.created_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—',
                status: c.status === 'processing' ? 'Draft' : 'Final',
                score: Math.round(c.fraud_confidence_score ?? 0),
                summary,
                recommendation,
                modalityExplanations,
                scoreBreakdown,
              }
            })
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
        <div style={{ width: 56, height: 56, borderRadius: 16, background: '#F9EEF1', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
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
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 120px 80px 110px 24px', gap: 0, padding: '8px 16px', background: C.bg, borderBottom: `1px solid ${C.border}` }}>
          {['Report Title', 'Date', 'Status', '', ''].map((h, i) => (
            <div key={i} style={{ fontSize: 10, fontWeight: 700, color: C.mutedLight, textTransform: 'uppercase' as const, letterSpacing: '0.05em' }}>{h}</div>
          ))}
        </div>

        {/* Rows */}
        {visible.map((r, i) => {
          const sel = selected === r.id
          return (
            <div key={r.id} style={{ borderBottom: i < visible.length - 1 ? `1px solid #FFFFFF` : 'none' }}>
              <div
                onClick={() => setSelected(sel ? null : r.id)}
                style={{ display: 'grid', gridTemplateColumns: '1fr 120px 80px 110px 24px', padding: '12px 16px', alignItems: 'center', cursor: 'pointer', background: sel ? '#F9EEF1' : '#fff', transition: 'background 0.1s' }}
              >
                <div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <FileText size={14} color={sel ? C.blue : C.mutedLight} />
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
                    onClick={e => e.stopPropagation()}
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 5,
                      padding: '5px 10px', borderRadius: 6, border: `1px solid ${C.border}`,
                      background: '#fff', color: C.muted, fontSize: 11, cursor: 'pointer', fontFamily: 'inherit',
                      textDecoration: 'none',
                    }}
                  >
                    <Download size={11} /> Download
                  </a>
                </div>
                <ChevronDown size={14} color={sel ? C.blue : C.mutedLight} style={{ transform: sel ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }} />
              </div>

              {/* Inline report detail — clicking any non-interactive area closes it */}
              {sel && (
                <div
                  onClick={e => {
                    const target = e.target as HTMLElement
                    if (target.closest('a, button, input, select, textarea')) return
                    setSelected(null)
                  }}
                  style={{ background: C.bg, borderTop: `1px solid ${C.border}`, padding: '16px 20px', cursor: 'pointer' }}
                >
                  <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 10, padding: 16 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
                      <div>
                        <div style={{ fontSize: 12, fontFamily: 'monospace', color: C.muted, marginBottom: 3 }}>{r.id} · {r.claimNumber}</div>
                        <div style={{ fontSize: 16, fontWeight: 800, color: C.text }}>{r.claimant}</div>
                        <div style={{ fontSize: 10, color: C.mutedLight, marginTop: 2 }}>Generated {r.date}</div>
                      </div>
                      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                        <StatusPill status={r.status.toLowerCase() as any} size="xs" />
                        <span style={{ fontSize: 12, fontWeight: 700, color: r.score > 85 ? C.red : r.score >= 15 ? C.amber : C.green }}>
                          Fraud Score: {r.score}
                        </span>
                      </div>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                      {!r.summary && r.modalityExplanations.length === 0 && !r.scoreBreakdown && (
                        <div style={{ fontSize: 11, color: C.mutedLight }}>No report details are available for this claim yet.</div>
                      )}

                      {r.summary && (
                        <div>
                          <SectionHeading>AI Analysis Summary</SectionHeading>
                          <div style={{ fontSize: 12, color: C.textSub, lineHeight: 1.6, background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8, padding: '10px 12px' }}>
                            {r.summary}
                          </div>
                        </div>
                      )}

                      {r.modalityExplanations.length > 0 && (
                        <div>
                          <SectionHeading>Modality Analysis</SectionHeading>
                          {r.modalityExplanations.map(m => (
                            <div key={m.modality} style={{ border: `1px solid ${C.border}`, borderRadius: 7, padding: '8px 10px', marginBottom: 6, background: '#fff' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                                <span style={{ fontSize: 10, fontWeight: 700, color: C.text, textTransform: 'capitalize' as const }}>{m.modality}</span>
                                <span style={{ fontSize: 10, fontWeight: 700, color: m.score > 85 ? C.red : m.score >= 15 ? C.amber : C.green }}>{Math.round(m.score)}%</span>
                              </div>
                              <div style={{ fontSize: 10, color: C.muted, lineHeight: 1.5 }}>{m.explanation}</div>
                            </div>
                          ))}
                        </div>
                      )}

                      {r.recommendation && (
                        <div style={{ fontSize: 11, color: C.textSub, fontStyle: 'italic' as const }}>{r.recommendation}</div>
                      )}

                      {r.scoreBreakdown && <ScoreBreakdownPanel breakdown={r.scoreBreakdown} />}

                      <a
                        href={getReportPdfUrl(r.claimId)}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, padding: '9px', borderRadius: 7, border: `1px solid ${C.border}`, background: '#fff', color: C.muted, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', textDecoration: 'none', marginTop: 4 }}
                      >
                        <Download size={13} /> Download Report PDF
                      </a>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
