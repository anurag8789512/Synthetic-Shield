import { useState, useEffect } from 'react'
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { C, SectionHeading } from '../common/ui'
import { fetchAllClaims } from '../../data/api'

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 8, padding: '8px 12px', fontSize: 11, boxShadow: '0 4px 16px rgba(0,0,0,0.08)' }}>
      <div style={{ fontWeight: 700, color: C.text, marginBottom: 4 }}>{label}</div>
      {payload.map((p: any, i: number) => (
        <div key={i} style={{ color: p.color, marginBottom: 2 }}>{p.name}: <strong>{p.value}</strong></div>
      ))}
    </div>
  )
}

const MODALITY_LABELS: Record<string, string> = {
  video: 'Video Deepfake',
  audio: 'Voice Clone',
  image: 'Photo Manipulation',
  text: 'Narrative (AI Text)',
}

export default function Analytics() {
  const [claims, setClaims] = useState<any[]>([])

  useEffect(() => {
    let active = true
    const load = async () => {
      const data = await fetchAllClaims()
      if (active && Array.isArray(data)) setClaims(data)
    }
    load()
    const interval = setInterval(load, 10000)
    return () => { active = false; clearInterval(interval) }
  }, [])

  // ── KPIs ──
  const total = claims.length
  const flagged = claims.filter(c => (c.fraud_confidence_score ?? 0) > 85).length
  const autoApproved = claims.filter(c => c.status === 'auto_approved').length
  const scored = claims.filter(c => c.fraud_confidence_score != null)
  const avgScore = scored.length ? scored.reduce((s, c) => s + c.fraud_confidence_score, 0) / scored.length : 0

  const kpis = [
    { label: 'Claims Processed', value: String(total), sub: 'All time' },
    { label: 'Flagged for SIU', value: String(flagged), sub: 'Score > 85%' },
    { label: 'Auto-Approved', value: String(autoApproved), sub: 'Score < 15%' },
    { label: 'Avg Fraud Score', value: scored.length ? `${avgScore.toFixed(1)}%` : '—', sub: 'Across analyzed claims' },
  ]

  // ── Volume trend (last 14 days) ──
  const volumeTrend = (() => {
    const days: { date: string; total: number; flagged: number }[] = []
    for (let i = 13; i >= 0; i--) {
      const d = new Date()
      d.setDate(d.getDate() - i)
      const key = d.toDateString()
      const label = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
      const dayClaims = claims.filter(c => c.created_at && new Date(c.created_at).toDateString() === key)
      days.push({
        date: label,
        total: dayClaims.length,
        flagged: dayClaims.filter(c => (c.fraud_confidence_score ?? 0) > 85).length,
      })
    }
    return days
  })()

  // ── Outcome distribution ──
  const outcomeDist = [
    { name: 'Auto-Approved', value: claims.filter(c => ['auto_approved'].includes(c.status)).length, color: '#10B981' },
    { name: 'Manual Review', value: claims.filter(c => ['moderator_review', 'rejected'].includes(c.status)).length, color: '#F59E0B' },
    { name: 'SIU Investigation', value: claims.filter(c => ['siu_investigation', 'siu_confirmed_fraud', 'siu_cleared'].includes(c.status)).length, color: '#EF4444' },
    { name: 'Processing', value: claims.filter(c => c.status === 'processing').length, color: '#8A8A8A' },
  ].filter(d => d.value > 0)

  // ── Signal breakdown (per-modality anomalies, score > 50) ──
  const signalBreakdown = (() => {
    const counts: Record<string, number> = {}
    for (const c of claims) {
      for (const a of c.analyses || []) {
        if ((a.raw_score ?? 0) > 50) {
          const label = MODALITY_LABELS[a.modality] || a.modality
          counts[label] = (counts[label] || 0) + 1
        }
      }
    }
    return Object.entries(counts).map(([type, count]) => ({ type, count }))
  })()

  const empty = total === 0

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 20, background: C.bg }}>

      {/* KPI cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
        {kpis.map(k => (
          <div key={k.label} style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 10, padding: '16px' }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: C.muted, marginBottom: 8 }}>{k.label}</div>
            <div style={{ fontSize: 26, fontWeight: 800, color: C.text, lineHeight: 1 }}>{k.value}</div>
            <div style={{ fontSize: 10, color: C.mutedLight, marginTop: 4 }}>{k.sub}</div>
          </div>
        ))}
      </div>

      {empty && (
        <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 10, padding: '32px', textAlign: 'center', marginBottom: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: C.text, marginBottom: 4 }}>No analytics yet</div>
          <div style={{ fontSize: 11, color: C.muted }}>Charts populate automatically as claims are submitted and analyzed.</div>
        </div>
      )}

      {/* Charts row */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12, marginBottom: 12 }}>

        {/* Area chart: volume trend */}
        <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 10, padding: '16px' }}>
          <div style={{ marginBottom: 14 }}>
            <SectionHeading>Claims Volume — Last 14 Days</SectionHeading>
            <div style={{ fontSize: 12, color: C.muted }}>Total claims submitted vs. flagged for SIU</div>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={volumeTrend} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="gradTotal" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={C.primary} stopOpacity={0.15} />
                  <stop offset="95%" stopColor={C.primary} stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradFlagged" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={C.red} stopOpacity={0.12} />
                  <stop offset="95%" stopColor={C.red} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#F3F0F1" vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: C.mutedLight }} axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: C.mutedLight }} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 11, color: C.muted, paddingTop: 8 }} />
              <Area type="monotone" dataKey="total"   name="Total Claims"   stroke={C.primary} strokeWidth={2} fill="url(#gradTotal)"   dot={false} />
              <Area type="monotone" dataKey="flagged" name="Flagged Claims" stroke={C.red}     strokeWidth={2} fill="url(#gradFlagged)" dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Donut: outcome distribution */}
        <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 10, padding: '16px' }}>
          <div style={{ marginBottom: 14 }}>
            <SectionHeading>Claim Outcome Distribution</SectionHeading>
            <div style={{ fontSize: 12, color: C.muted }}>{total} claim{total === 1 ? '' : 's'} total</div>
          </div>
          {outcomeDist.length === 0 ? (
            <div style={{ height: 160, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, color: C.mutedLight }}>No outcomes yet</div>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={160}>
                <PieChart>
                  <Pie data={outcomeDist} cx="50%" cy="50%" innerRadius={48} outerRadius={72} paddingAngle={2} dataKey="value">
                    {outcomeDist.map((d, i) => <Cell key={i} fill={d.color} />)}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
                {outcomeDist.map(d => (
                  <div key={d.name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                      <div style={{ width: 8, height: 8, borderRadius: '50%', background: d.color }} />
                      <span style={{ fontSize: 11, color: C.textSub }}>{d.name}</span>
                    </div>
                    <span style={{ fontSize: 11, fontWeight: 700, color: C.text }}>{d.value}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Bar chart: fraud signal breakdown */}
      <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 10, padding: '16px' }}>
        <div style={{ marginBottom: 14 }}>
          <SectionHeading>Fraud Signal Breakdown</SectionHeading>
          <div style={{ fontSize: 12, color: C.muted }}>Detection signals scoring above 50% by modality</div>
        </div>
        {signalBreakdown.length === 0 ? (
          <div style={{ height: 180, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, color: C.mutedLight }}>No elevated signals detected yet</div>
        ) : (
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={signalBreakdown} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F3F0F1" vertical={false} />
              <XAxis dataKey="type" tick={{ fontSize: 11, fill: C.mutedLight }} axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: C.mutedLight }} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} cursor={{ fill: '#FFFFFF' }} />
              <Bar dataKey="count" name="Claims Flagged" radius={[4, 4, 0, 0]}>
                {signalBreakdown.map((_, i) => (
                  <Cell key={i} fill={[C.red, C.amber, C.primary, C.muted][i % 4]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
