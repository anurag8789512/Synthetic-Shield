import { useState, useEffect, useCallback, Fragment } from 'react'
import { Users, BarChart3, CheckCircle, Clock, TrendingUp, ChevronDown, ArrowRightLeft } from 'lucide-react'
import { C } from '../common/ui'
import { fetchOfficers, fetchWorkloadSummary, fetchOfficerAssignments, reassignAssignment } from '../../data/api'

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

interface PendingAssignment {
  id: number
  claim_id: number
  claim_number: string
  claim_status: string
  fraud_score: number | null
  assignment_type: string
  status: string
  assigned_at: string | null
}

export default function Efficiency() {
  const [officers, setOfficers] = useState<OfficerStats[]>([])
  const [summary, setSummary] = useState<WorkloadSummary | null>(null)
  const [detailsFor, setDetailsFor] = useState<number | null>(null)
  const [pending, setPending] = useState<PendingAssignment[]>([])
  const [detailsLoading, setDetailsLoading] = useState(false)
  const [reassignSel, setReassignSel] = useState<Record<number, number>>({})
  const [busyId, setBusyId] = useState<number | null>(null)
  const [reassignError, setReassignError] = useState('')

  const isSenior = sessionStorage.getItem('ss_officer_role') === 'senior'

  const load = useCallback(async () => {
    try {
      // Both endpoints require an officer session token — always go through
      // data/api.ts so the Authorization header is attached.
      const [offs, sum] = await Promise.all([fetchOfficers(), fetchWorkloadSummary()])
      if (Array.isArray(offs)) setOfficers(offs)
      if (sum) setSummary(sum)
    } catch {}
  }, [])

  useEffect(() => {
    load()
    const interval = setInterval(load, 10000)
    return () => clearInterval(interval)
  }, [load])

  const loadDetails = useCallback(async (officerId: number) => {
    setDetailsLoading(true)
    const data = await fetchOfficerAssignments(officerId)
    setPending(((data?.assignments || []) as PendingAssignment[]).filter(a => a.status === 'pending'))
    setDetailsLoading(false)
  }, [])

  const toggleDetails = (officerId: number) => {
    setReassignError('')
    setReassignSel({})
    if (detailsFor === officerId) {
      setDetailsFor(null)
      return
    }
    setDetailsFor(officerId)
    setPending([])
    loadDetails(officerId)
  }

  const doReassign = async (a: PendingAssignment) => {
    const target = reassignSel[a.id]
    if (!target || detailsFor === null) return
    setBusyId(a.id)
    setReassignError('')
    const res = await reassignAssignment(a.id, target)
    if (!res.ok) {
      setReassignError(res.detail || 'Reassignment failed.')
    } else {
      await Promise.all([loadDetails(detailsFor), load()])
    }
    setBusyId(null)
  }

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
              {isSenior && (
                <th style={{ textAlign: 'center', padding: '8px 14px', fontWeight: 600, color: C.muted, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Details</th>
              )}
            </tr>
          </thead>
          <tbody>
            {officers.map(o => {
              const open = detailsFor === o.id
              return (
                <Fragment key={o.id}>
                  <tr style={{ borderBottom: `1px solid ${C.border}`, background: open ? '#F8FAFC' : '#fff' }}>
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
                {isSenior && (
                  <td style={{ textAlign: 'center', padding: '10px 14px' }}>
                    <button
                      onClick={() => toggleDetails(o.id)}
                      style={{
                        display: 'inline-flex', alignItems: 'center', gap: 4, padding: '5px 10px',
                        borderRadius: 6, border: `1px solid ${open ? C.blue : C.border}`,
                        background: open ? '#EFF6FF' : '#fff', color: open ? C.blue : C.muted,
                        fontSize: 11, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
                      }}
                    >
                      Details <ChevronDown size={12} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }} />
                    </button>
                  </td>
                )}
              </tr>

              {/* Senior-only dropdown: pending claims + reassignment */}
              {isSenior && open && (
                <tr>
                  <td colSpan={9} style={{ padding: 0, borderBottom: `1px solid ${C.border}` }}>
                    <div style={{ background: C.bg, padding: '14px 20px' }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: C.text, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
                        <ArrowRightLeft size={13} color={C.blue} /> Pending claims assigned to {o.name}
                      </div>

                      {detailsLoading && <div style={{ fontSize: 11, color: C.mutedLight }}>Loading assignments…</div>}
                      {!detailsLoading && pending.length === 0 && (
                        <div style={{ fontSize: 11, color: C.mutedLight }}>No pending assignments for this officer.</div>
                      )}

                      {!detailsLoading && pending.length > 0 && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                          {pending.map(a => {
                            const eligible = officers.filter(t =>
                              t.id !== o.id &&
                              (a.assignment_type !== 'siu_vote' || t.role === 'siu_officer' || t.role === 'senior')
                            )
                            return (
                              <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 12, background: '#fff', border: `1px solid ${C.border}`, borderRadius: 8, padding: '10px 14px' }}>
                                <div style={{ width: 130 }}>
                                  <div style={{ fontSize: 11, fontFamily: 'monospace', fontWeight: 700, color: C.text }}>{a.claim_number}</div>
                                  <div style={{ fontSize: 9, color: C.mutedLight, marginTop: 2 }}>
                                    Assigned {a.assigned_at ? new Date(a.assigned_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short' }) : '—'}
                                  </div>
                                </div>
                                <div style={{ width: 120 }}>
                                  <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 4, background: a.assignment_type === 'siu_vote' ? '#FFF5F5' : '#FFFBEB', color: a.assignment_type === 'siu_vote' ? C.red : C.amber }}>
                                    {a.assignment_type === 'siu_vote' ? 'SIU Vote' : 'Moderator Review'}
                                  </span>
                                </div>
                                <div style={{ width: 90, fontSize: 10, color: C.muted }}>
                                  Score: <span style={{ fontWeight: 700, color: (a.fraud_score ?? 0) > 85 ? C.red : (a.fraud_score ?? 0) >= 15 ? C.amber : C.green }}>{a.fraud_score != null ? Math.round(a.fraud_score) : '—'}</span>
                                </div>
                                <div style={{ flex: 1 }} />
                                <select
                                  value={reassignSel[a.id] ?? ''}
                                  onChange={e => setReassignSel(s => ({ ...s, [a.id]: Number(e.target.value) }))}
                                  style={{ height: 30, border: `1px solid ${C.border}`, borderRadius: 6, fontSize: 11, padding: '0 8px', fontFamily: 'inherit', color: C.text, background: '#fff', outline: 'none' }}
                                >
                                  <option value="" disabled>Reassign to…</option>
                                  {eligible.map(t => (
                                    <option key={t.id} value={t.id}>{t.name} ({t.pending_assignments} pending)</option>
                                  ))}
                                </select>
                                <button
                                  onClick={() => doReassign(a)}
                                  disabled={!reassignSel[a.id] || busyId === a.id}
                                  style={{
                                    display: 'inline-flex', alignItems: 'center', gap: 5, padding: '6px 12px', borderRadius: 6,
                                    border: 'none', background: !reassignSel[a.id] || busyId === a.id ? '#CBD5E1' : C.blue,
                                    color: '#fff', fontSize: 11, fontWeight: 600,
                                    cursor: !reassignSel[a.id] || busyId === a.id ? 'not-allowed' : 'pointer', fontFamily: 'inherit',
                                  }}
                                >
                                  <ArrowRightLeft size={11} /> {busyId === a.id ? 'Reassigning…' : 'Reassign'}
                                </button>
                              </div>
                            )
                          })}
                        </div>
                      )}

                      {reassignError && (
                        <div style={{ fontSize: 11, color: C.red, marginTop: 8, fontWeight: 600 }}>{reassignError}</div>
                      )}
                    </div>
                  </td>
                </tr>
              )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
