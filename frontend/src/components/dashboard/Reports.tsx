import { useState } from 'react'
import { Download, FileText, Filter } from 'lucide-react'
import { REPORTS } from '../../data/mock'
import { StatusPill, C } from '../common/ui'
import { getDownloadReportUrl } from '../../data/api'

const TYPES = ['All Types', 'Fraud Pattern Analysis', 'Investigation Summary', 'Monthly Digest']

export default function Reports() {
  const [typeFilter, setTypeFilter] = useState('All Types')
  const [search, setSearch] = useState('')

  const visible = REPORTS.filter(r =>
    (typeFilter === 'All Types' || r.type === typeFilter) &&
    (!search || r.title.toLowerCase().includes(search.toLowerCase()) || r.id.toLowerCase().includes(search.toLowerCase()))
  )

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 20, background: C.bg }}>
      <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 10, overflow: 'hidden' }}>
        {/* Toolbar */}
        <div style={{ padding: '12px 16px', borderBottom: `1px solid ${C.border}`, display: 'flex', gap: 10, alignItems: 'center' }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: C.text, marginRight: 8 }}>Reports</div>

          <div style={{ position: 'relative' }}>
            <Filter size={12} color={C.mutedLight} style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)' }} />
            <select
              value={typeFilter} onChange={e => setTypeFilter(e.target.value)}
              style={{ height: 32, background: C.bg, border: `1px solid ${C.border}`, borderRadius: 7, fontSize: 12, padding: '0 10px 0 28px', outline: 'none', fontFamily: 'inherit', color: C.text, appearance: 'none' as const, paddingRight: 20, cursor: 'pointer' }}
            >
              {TYPES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>

          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search reports…"
            style={{ height: 32, background: C.bg, border: `1px solid ${C.border}`, borderRadius: 7, fontSize: 12, padding: '0 10px', outline: 'none', fontFamily: 'inherit', color: C.text, width: 200 }}
          />

          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 11, color: C.mutedLight }}>{visible.length} reports</span>
        </div>

        {/* Table header */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 200px 120px 80px 70px 110px', gap: 0, padding: '8px 16px', background: C.bg, borderBottom: `1px solid ${C.border}` }}>
          {['Report Title', 'Type', 'Date', 'Status', 'Pages', ''].map(h => (
            <div key={h} style={{ fontSize: 10, fontWeight: 700, color: C.mutedLight, textTransform: 'uppercase' as const, letterSpacing: '0.05em' }}>{h}</div>
          ))}
        </div>

        {/* Rows */}
        {visible.map((r, i) => (
          <div key={r.id} style={{ display: 'grid', gridTemplateColumns: '1fr 200px 120px 80px 70px 110px', padding: '12px 16px', borderBottom: i < visible.length - 1 ? `1px solid #F8FAFC` : 'none', alignItems: 'center' }}>
            <div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <FileText size={14} color={C.mutedLight} />
                <div style={{ fontSize: 12, fontWeight: 600, color: C.text }}>{r.title}</div>
              </div>
              <div style={{ fontSize: 9, color: C.mutedLight, fontFamily: 'monospace', marginTop: 2, marginLeft: 22 }}>{r.id}</div>
            </div>
            <div style={{ fontSize: 11, color: C.textSub }}>{r.type}</div>
            <div style={{ fontSize: 11, color: C.muted }}>{r.date}</div>
            <div>
              <StatusPill status={r.status.toLowerCase() as any} size="xs" />
            </div>
            <div style={{ fontSize: 11, color: C.muted }}>{r.pages}p</div>
            <div>
              <a
                href={getDownloadReportUrl(r.id, r.title, r.type, r.date, r.pages, r.status)}
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
