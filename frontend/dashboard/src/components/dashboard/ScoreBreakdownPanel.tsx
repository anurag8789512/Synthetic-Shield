import { useState } from 'react'
import { ChevronDown, ChevronRight, Layers } from 'lucide-react'
import { type ScoreBreakdown, type ScoreSignal } from '../../data/types'
import { SectionHeading, C } from '../common/ui'

const LEVELS: { id: string; label: string; signals: string[] }[] = [
  { id: 'l1', label: 'Level 1 · Metadata Analysis', signals: ['metadata'] },
  { id: 'l2', label: 'Level 2 · AI Manipulation', signals: ['image', 'video', 'audio', 'text'] },
  { id: 'l3', label: 'Level 3 · Consistency Check', signals: ['consistency'] },
]

function scoreColor(v: number) {
  return v > 70 ? C.red : v > 30 ? '#D97706' : C.green
}

function SignalRow({ s }: { s: ScoreSignal }) {
  const [open, setOpen] = useState(false)
  const hasDetail = s.findings.length > 0 || !!s.components
  const na = s.status !== 'ok' || s.value == null
  return (
    <div style={{ borderTop: `1px solid #F1F5F9` }}>
      <div
        onClick={() => hasDetail && setOpen(o => !o)}
        style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 10px', cursor: hasDetail ? 'pointer' : 'default' }}
      >
        {hasDetail
          ? (open ? <ChevronDown size={11} color={C.mutedLight} /> : <ChevronRight size={11} color={C.mutedLight} />)
          : <span style={{ width: 11 }} />}
        <span style={{ fontSize: 10.5, fontWeight: 600, color: C.text, width: 78, textTransform: 'capitalize' as const }}>{s.name}</span>
        {na ? (
          <span style={{ fontSize: 9.5, color: C.mutedLight, fontStyle: 'italic', flex: 1 }}>
            {s.status === 'not_applicable' ? 'not applicable' : 'unavailable'}
          </span>
        ) : (
          <>
            <div style={{ flex: 1, height: 5, background: '#F1F5F9', borderRadius: 3, overflow: 'hidden' }}>
              <div style={{ width: `${Math.min(s.value!, 100)}%`, height: '100%', background: scoreColor(s.value!), borderRadius: 3 }} />
            </div>
            <span style={{ fontSize: 10.5, fontWeight: 700, color: scoreColor(s.value!), width: 34, textAlign: 'right' as const, fontFamily: 'monospace' }}>
              {s.value!.toFixed(0)}
            </span>
          </>
        )}
        <span style={{ fontSize: 9, color: C.mutedLight, width: 40, textAlign: 'right' as const, fontFamily: 'monospace' }}>
          {s.weight != null ? `${(s.weight * 100).toFixed(0)}% wt` : '—'}
        </span>
      </div>
      {open && hasDetail && (
        <div style={{ padding: '2px 10px 9px 29px', display: 'flex', flexDirection: 'column', gap: 4 }}>
          {s.components && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {Object.entries(s.components).map(([k, v]) => (
                <span key={k} style={{ fontSize: 8.5, padding: '2px 7px', borderRadius: 4, background: '#F8FAFC', border: `1px solid ${C.border}`, color: C.textSub, fontFamily: 'monospace' }}>
                  {k}: {typeof v === 'number' ? v.toFixed(0) : String(v)}
                </span>
              ))}
            </div>
          )}
          {s.findings.map((f, i) => (
            <div key={i} style={{ fontSize: 9.5, color: C.textSub, lineHeight: 1.5 }}>• {f}</div>
          ))}
        </div>
      )}
    </div>
  )
}

export function ScoreBreakdownPanel({ breakdown }: { breakdown: ScoreBreakdown }) {
  return (
    <div>
      <SectionHeading>Score Division by Level</SectionHeading>
      <div style={{ border: `1px solid ${C.border}`, borderRadius: 8, overflow: 'hidden', background: '#fff' }}>
        {LEVELS.map(level => {
          const signals = breakdown.signals.filter(s => level.signals.includes(s.name))
          if (signals.length === 0) return null
          return (
            <div key={level.id}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 10px', background: '#F8FAFC' }}>
                <Layers size={10} color={C.muted} />
                <span style={{ fontSize: 9, fontWeight: 700, color: C.muted, textTransform: 'uppercase' as const, letterSpacing: '0.05em' }}>
                  {level.label}
                </span>
              </div>
              {signals.map(s => <SignalRow key={s.name} s={s} />)}
            </div>
          )
        })}
        {/* Fusion summary */}
        <div style={{ borderTop: `1px solid ${C.border}`, padding: '8px 10px', background: '#FAFBFC', display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
          <span style={{ fontSize: 10, color: C.textSub }}>
            Base <strong style={{ fontFamily: 'monospace' }}>{breakdown.baseScore.toFixed(1)}</strong>
          </span>
          <span style={{ fontSize: 10, color: C.textSub }}>
            Final <strong style={{ fontFamily: 'monospace', color: scoreColor(breakdown.finalScore) }}>{breakdown.finalScore.toFixed(1)}</strong>
          </span>
          <span style={{ fontSize: 9, padding: '2px 8px', borderRadius: 10, fontWeight: 700, background: breakdown.routingBand === 'SIU_INVESTIGATION' ? '#FFF5F5' : breakdown.routingBand === 'AUTO_APPROVE' ? '#F0FDF4' : '#FFFBEB', color: breakdown.routingBand === 'SIU_INVESTIGATION' ? '#DC2626' : breakdown.routingBand === 'AUTO_APPROVE' ? '#059669' : '#D97706' }}>
            {breakdown.routingBand.replace(/_/g, ' ')}
          </span>
          {breakdown.escalated && (
            <span style={{ fontSize: 9, color: '#DC2626', fontWeight: 600 }}>
              ⚠ worst-signal escalation via {breakdown.escalationSource}
            </span>
          )}
          {breakdown.forcedReviewReason && (
            <span style={{ fontSize: 9, color: '#D97706' }}>forced review: {breakdown.forcedReviewReason}</span>
          )}
        </div>
      </div>
    </div>
  )
}
