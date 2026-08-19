import { useState, useEffect } from 'react'
import { Users, BarChart3, CheckCircle, Clock, TrendingUp } from 'lucide-react'
import { C } from '../common/ui'

const API = 'http://localhost:8000'

interface OfficerStats {
  id: number
  name: string
  email: string
  role: string
  department: string
  pending_assignments: number
  completed_assignments: number
  moderator_approved: number
  moderator_rejected: number
  siu_fraud_votes: number
  siu_clear_votes: number
  total_decisions: number
  utilization: number
}

interface WorkloadSummary {
  total_officers: number
  total_pending_assignments: number
  total_completed_assignments: number
  max_officer_load: number
  min_officer_load: number
  load_balance_score: number
  officer_loads: { name: string; pending: number }[]
}

export default function Efficiency() {
  const [officers, setOfficers] = useState<OfficerStats[]>([])
  const [summary, setSummary] = useState<WorkloadSummary | null>(null)

  useEffect(() => {
    const load = async () => {
      try {
        const [offRes, sumRes] = await Promise.all([
          fetch(`${API}/efficiency/officers`),
          fetch(`${API}/efficiency/workload-summary`),
        ])
        if (offRes.ok) setOfficers(await offRes.json())
        if (sumRes.ok) setSummary(await sumRes.json())
      } catch {}
    }
    load()
    const interval = setInterval(load, 10000)
    return () => clearInterval(interval)
  }, [])

  const balanceColor = (summary?.load_balance_score ?? 100) > 80 ? C.green : (summary?.load_balance_score ?? 100) > 50 ? C.amber : C.red

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 20, background: C.bg }}>
      {/* KPI Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
        <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 10, padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <Users size={16} color={C.blue} />
            <span style={{ fontSize: 11, color: C.muted, fontWeight: 600 }}>Total Officers</span>
          </div>
          <div style={{ fontSize: 28, fontWeight: 800, color: C.text }}>{summary?.total_officers ?? '—'}</div>
        </div>
        <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 10, padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <Clock size={16} color={C.amber} />
            <span style={{ fontSize: 11, color: C.muted, fontWeight: 600 }}>Pending Tasks</span>
          </div>
          <div style={{ fontSize: 28, fontWeight: 800, color: C.text }}>{summary?.total_pending_assignments ?? '—'}</div>
        </div>
        <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 10, padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <CheckCircle size={16} color={C.green} />
            <span style={{ fontSize: 11, color: C.muted, fontWeight: 600 }}>Completed</span>
          </div>
          <div style={{ fontSize: 28, fontWeight: 800, color: C.text }}>{summary?.total_completed_assignments ?? '—'}</div>
        </div>
        <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 10, padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <TrendingUp size={16} color={balanceColor} />
            <span style={{ fontSize: 11, color: C.muted, fontWeight: 600 }}>Load Balance</span>
          </div>
          <div style={{ fontSize: 28, fontWeight: 800, color: balanceColor }}>{summary?.load_balance_score ?? '—'}%</div>
          <div style={{ fontSize: 10, color: C.mutedLight, marginTop: 2 }}>100% = perfectly balanced</div>
        </div>
      </div>

      {/* Workload distribution bar */}
      {summary && summary.officer_loads.length > 0 && (
        <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 10, padding: 16, marginBottom: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: C.text, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
            <BarChart3 size={15} color={C.blue} /> Workload Distribution
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {summary.officer_loads.map(ol => {
              const maxPending = Math.max(...summary.officer_loads.map(o => o.pending), 1)
              const pct = (ol.pending / maxPending) * 100
              const barColor = ol.pending === summary.max_officer_load && summary.max_officer_load > summary.min_officer_load + 2 ? C.red : C.blue
              return (
                <div key={ol.name} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{ width: 100, fontSize: 11, fontWeight: 600, color: C.text, flexShrink: 0 }}>{ol.name}</div>
                  <div style={{ flex: 1, height: 8, background: '#F1F5F9', borderRadius: 4, overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${pct}%`, background: barColor, borderRadius: 4, transition: 'width 0.3s' }} />
                  </div>
                  <div style={{ width: 30, fontSize: 11, fontWeight: 700, color: C.text, textAlign: 'right' }}>{ol.pending}</div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Officer table */}
      <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 10, overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', borderBottom: `1px solid ${C.border}`, fontSize: 13, fontWeight: 700, color: C.text }}>
          Officer Performance
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ background: '#F8FAFC' }}>
              <th style={{ textAlign: 'left', padding: '8px 14px', fontWeight: 600, color: C.muted, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Officer</th>
              <th style={{ textAlign: 'left', padding: '8px 14px', fontWeight: 600, color: C.muted, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Role</th>
              <th style={{ textAlign: 'center', padding: '8px 14px', fontWeight: 600, color: C.muted, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Pending</th>
              <th style={{ textAlign: 'center', padding: '8px 14px', fontWeight: 600, color: C.muted, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Completed</th>
              <th style={{ textAlign: 'center', padding: '8px 14px', fontWeight: 600, color: C.muted, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Mod ✓/✗</th>
              <th style={{ textAlign: 'center', padding: '8px 14px', fontWeight: 600, color: C.muted, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>SIU F/C</th>
              <th style={{ textAlign: 'center', padding: '8px 14px', fontWeight: 600, color: C.muted, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Total</th>
              <th style={{ textAlign: 'center', padding: '8px 14px', fontWeight: 600, color: C.muted, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Utilization</th>
            </tr>
          </thead>
          <tbody>
            {officers.map(o => (
              <tr key={o.id} style={{ borderBottom: `1px solid ${C.border}` }}>
                <td style={{ padding: '10px 14px' }}>
                  <div style={{ fontWeight: 600, color: C.text }}>{o.name}</div>
                  <div style={{ fontSize: 10, color: C.mutedLight }}>{o.email}</div>
                </td>
                <td style={{ padding: '10px 14px' }}>
                  <span style={{
                    fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 4,
                    background: o.role === 'senior' ? '#EFF6FF' : o.role === 'siu_officer' ? '#FFF5F5' : '#FFFBEB',
                    color: o.role === 'senior' ? C.blue : o.role === 'siu_officer' ? C.red : C.amber,
                  }}>
                    {o.role}
                  </span>
                </td>
                <td style={{ textAlign: 'center', padding: '10px 14px', fontWeight: 700, color: o.pending_assignments > 3 ? C.red : C.text }}>
                  {o.pending_assignments}
                </td>
                <td style={{ textAlign: 'center', padding: '10px 14px', color: C.text }}>{o.completed_assignments}</td>
                <td style={{ textAlign: 'center', padding: '10px 14px' }}>
                  <span style={{ color: C.green, fontWeight: 600 }}>{o.moderator_approved}</span>
                  <span style={{ color: C.mutedLight }}> / </span>
                  <span style={{ color: C.red, fontWeight: 600 }}>{o.moderator_rejected}</span>
                </td>
                <td style={{ textAlign: 'center', padding: '10px 14px' }}>
                  <span style={{ color: C.red, fontWeight: 600 }}>{o.siu_fraud_votes}</span>
                  <span style={{ color: C.mutedLight }}> / </span>
                  <span style={{ color: C.green, fontWeight: 600 }}>{o.siu_clear_votes}</span>
                </td>
                <td style={{ textAlign: 'center', padding: '10px 14px', fontWeight: 700, color: C.blue }}>{o.total_decisions}</td>
                <td style={{ textAlign: 'center', padding: '10px 14px' }}>
                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                    <div style={{ width: 40, height: 4, background: '#F1F5F9', borderRadius: 2, overflow: 'hidden' }}>
                      <div style={{ height: '100%', width: `${o.utilization}%`, background: o.utilization > 70 ? C.red : o.utilization > 40 ? C.amber : C.green, borderRadius: 2 }} />
                    </div>
                    <span style={{ fontSize: 10, fontWeight: 600, color: C.muted }}>{o.utilization}%</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
