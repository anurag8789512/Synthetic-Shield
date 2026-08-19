import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { VOLUME_TREND, OUTCOME_DIST, SIGNAL_BREAKDOWN } from '../../data/mock'
import { C, SectionHeading } from '../common/ui'

const KPI_DATA = [
  { label: 'Claims Processed',       value: '247',      sub: 'This month',     trend: 'up',   delta: '+12%' },
  { label: 'Fraud Prevented',        value: '$124,500', sub: 'Estimated value', trend: 'up',   delta: '+8%'  },
  { label: 'Detection Accuracy',     value: '99.2%',    sub: 'Last 30 days',   trend: 'flat', delta: '—'    },
  { label: 'Avg Processing Time',    value: '3.2s',     sub: 'Per claim',       trend: 'down', delta: '−5%'  },
]

function TrendIcon({ trend }: { trend: string }) {
  if (trend === 'up')   return <TrendingUp size={14} color={C.green} />
  if (trend === 'down') return <TrendingDown size={14} color={C.red} />
  return <Minus size={14} color={C.muted} />
}

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

export default function Analytics() {
  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 20, background: C.bg }}>

      {/* KPI cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
        {KPI_DATA.map(k => (
          <div key={k.label} style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 10, padding: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: C.muted }}>{k.label}</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <TrendIcon trend={k.trend} />
                <span style={{ fontSize: 11, fontWeight: 700, color: k.trend === 'up' ? C.green : k.trend === 'down' ? C.red : C.muted }}>{k.delta}</span>
              </div>
            </div>
            <div style={{ fontSize: 26, fontWeight: 800, color: C.text, lineHeight: 1 }}>{k.value}</div>
            <div style={{ fontSize: 10, color: C.mutedLight, marginTop: 4 }}>{k.sub}</div>
          </div>
        ))}
      </div>

      {/* Charts row */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12, marginBottom: 12 }}>

        {/* Area chart: volume trend */}
        <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 10, padding: '16px' }}>
          <div style={{ marginBottom: 14 }}>
            <SectionHeading>Claims Volume — Last 14 Days</SectionHeading>
            <div style={{ fontSize: 12, color: C.muted }}>Total claims submitted vs. flagged for review</div>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={VOLUME_TREND} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
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
              <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: C.mutedLight }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: C.mutedLight }} axisLine={false} tickLine={false} />
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
            <div style={{ fontSize: 12, color: C.muted }}>247 claims this month</div>
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <PieChart>
              <Pie data={OUTCOME_DIST} cx="50%" cy="50%" innerRadius={48} outerRadius={72} paddingAngle={2} dataKey="value">
                {OUTCOME_DIST.map((d, i) => <Cell key={i} fill={d.color} />)}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
            </PieChart>
          </ResponsiveContainer>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
            {OUTCOME_DIST.map(d => (
              <div key={d.name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <div style={{ width: 8, height: 8, borderRadius: '50%', background: d.color }} />
                  <span style={{ fontSize: 11, color: C.textSub }}>{d.name}</span>
                </div>
                <span style={{ fontSize: 11, fontWeight: 700, color: C.text }}>{d.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Bar chart: fraud signal breakdown */}
      <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 10, padding: '16px' }}>
        <div style={{ marginBottom: 14 }}>
          <SectionHeading>Fraud Signal Breakdown</SectionHeading>
          <div style={{ fontSize: 12, color: C.muted }}>Number of claims flagged by signal type this month</div>
        </div>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={SIGNAL_BREAKDOWN} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" vertical={false} />
            <XAxis dataKey="type" tick={{ fontSize: 11, fill: C.mutedLight }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 10, fill: C.mutedLight }} axisLine={false} tickLine={false} />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: '#F8FAFC' }} />
            <Bar dataKey="count" name="Claims Flagged" radius={[4, 4, 0, 0]}>
              {SIGNAL_BREAKDOWN.map((_, i) => (
                <Cell key={i} fill={[C.red, C.amber, C.primary, C.muted][i % 4]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
