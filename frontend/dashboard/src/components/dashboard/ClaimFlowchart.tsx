import { useState, useEffect } from 'react'
import { CheckCircle, AlertTriangle, Shield, Clock, FileText, Send, XCircle, Loader, Download } from 'lucide-react'
import { C } from '../common/ui'
import { fetchAllClaims, getReportPdfUrl } from '../../data/api'
import { serverDate } from '../../data/time'

const ACTION_CONFIG: Record<string, { icon: any; color: string; label: string }> = {
  claim_received: { icon: FileText, color: '#800020', label: 'Claim Submitted' },
  detection_completed: { icon: Shield, color: '#6E1423', label: 'AI Detection Completed' },
  adjudication_routed: { icon: AlertTriangle, color: '#F59E0B', label: 'Adjudication Decision' },
  payout_initiated: { icon: CheckCircle, color: '#10B981', label: 'Payout Initiated' },
  notification_sent: { icon: Send, color: '#800020', label: 'Notification Sent' },
  moderator_approved: { icon: CheckCircle, color: '#10B981', label: 'Moderator Approved' },
  moderator_rejected: { icon: XCircle, color: '#EF4444', label: 'Moderator Rejected' },
  siu_vote_cast: { icon: AlertTriangle, color: '#DC2626', label: 'SIU Vote Cast' },
  siu_finalized: { icon: Shield, color: '#DC2626', label: 'SIU Case Finalized' },
}

function getActionConfig(action: string) {
  return ACTION_CONFIG[action] || { icon: Clock, color: C.muted, label: action.replace(/_/g, ' ') }
}

interface AuditStep {
  action: string
  actor_type: string
  actor_id: string
  details_json: string | null
  created_at: string | null
}

interface ClaimWithTrail {
  id: number
  claim_number: string
  claimant_name: string
  status: string
  fraud_confidence_score: number | null
  audit_trail: AuditStep[]
}

export default function ClaimFlowchart() {
  const [claims, setClaims] = useState<ClaimWithTrail[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      const data = await fetchAllClaims()
      if (Array.isArray(data)) {
        const withTrail = data.filter((c: any) => c.audit_trail && c.audit_trail.length > 0)
        setClaims(withTrail)
        // functional update: this closure is created once, so `selected` here is stale
        if (withTrail.length > 0) setSelected(prev => prev ?? withTrail[0].claim_number)
      }
      setLoading(false)
    }
    load()
    const interval = setInterval(load, 8000)
    return () => clearInterval(interval)
  }, [])

  const claim = claims.find(c => c.claim_number === selected)

  if (loading) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: C.bg }}>
        <Loader size={24} color={C.blue} style={{ animation: 'spin-slow 1s linear infinite' }} />
      </div>
    )
  }

  if (claims.length === 0) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: C.bg, flexDirection: 'column', gap: 8 }}>
        <Shield size={32} color={C.mutedLight} />
        <div style={{ fontSize: 13, color: C.muted }}>No claims with audit trails yet</div>
        <div style={{ fontSize: 11, color: C.mutedLight }}>Submit a claim from the mobile app to see the lifecycle flowchart</div>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '260px 1fr', overflow: 'hidden', minHeight: 0, background: C.bg }}>
      {/* Left: claim selector */}
      <div style={{ background: '#fff', borderRight: `1px solid ${C.border}`, overflowY: 'auto', padding: 12 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: C.text, marginBottom: 10 }}>Claim Lifecycle</div>
        {claims.map(c => {
          const sel = c.claim_number === selected
          const statusColor = c.status === 'auto_approved' ? C.green : c.status === 'siu_investigation' ? C.red : C.amber
          return (
            <div
              key={c.claim_number}
              onClick={() => setSelected(c.claim_number)}
              style={{
                padding: '10px 12px', borderRadius: 8, marginBottom: 4, cursor: 'pointer',
                background: sel ? '#F9EEF1' : '#fff',
                border: `1px solid ${sel ? '#E7C3CD' : '#F3F0F1'}`,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: C.text }}>{c.claim_number}</div>
                <div style={{ width: 6, height: 6, borderRadius: '50%', background: statusColor }} />
              </div>
              <div style={{ fontSize: 10, color: C.mutedLight, marginTop: 2 }}>{c.claimant_name}</div>
              <div style={{ fontSize: 9, color: C.muted, marginTop: 2 }}>{c.audit_trail.length} steps</div>
            </div>
          )
        })}
      </div>

      {/* Right: flowchart */}
      <div style={{ overflowY: 'auto', padding: 24 }}>
        {claim && (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <div>
                <div style={{ fontSize: 16, fontWeight: 700, color: C.text }}>{claim.claim_number}</div>
                <div style={{ fontSize: 12, color: C.muted, marginTop: 2 }}>{claim.claimant_name} · Score: {claim.fraud_confidence_score ?? '—'}%</div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <a
                  href={getReportPdfUrl(claim.id)}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 5, padding: '5px 12px',
                    borderRadius: 7, fontSize: 11, fontWeight: 600, cursor: 'pointer', textDecoration: 'none',
                    background: C.blue, color: '#fff', border: 'none',
                  }}
                >
                  <Download size={12} /> Download PDF
                </a>
                <div style={{
                  padding: '4px 12px', borderRadius: 20, fontSize: 11, fontWeight: 600,
                  background: claim.status === 'auto_approved' ? '#F0FDF4' : claim.status === 'siu_investigation' ? '#FFF5F5' : '#FFFBEB',
                  color: claim.status === 'auto_approved' ? '#059669' : claim.status === 'siu_investigation' ? '#DC2626' : '#D97706',
                  border: `1px solid ${claim.status === 'auto_approved' ? '#BBF7D0' : claim.status === 'siu_investigation' ? '#FECACA' : '#FDE68A'}`,
                }}>
                  {claim.status.replace(/_/g, ' ')}
                </div>
              </div>
            </div>

            {/* Flowchart steps */}
            <div style={{ position: 'relative', paddingLeft: 28 }}>
              {/* Vertical line */}
              <div style={{ position: 'absolute', left: 11, top: 12, bottom: 12, width: 2, background: '#E4E0E1', borderRadius: 1 }} />

              {claim.audit_trail.map((step, i) => {
                const config = getActionConfig(step.action)
                const Icon = config.icon
                const isLast = i === claim.audit_trail.length - 1
                let details: Record<string, any> = {}
                try { if (step.details_json) details = JSON.parse(step.details_json) } catch {}

                return (
                  <div key={i} style={{ position: 'relative', marginBottom: isLast ? 0 : 20, display: 'flex', gap: 14 }}>
                    {/* Node dot */}
                    <div style={{
                      position: 'absolute', left: -28, top: 2,
                      width: 22, height: 22, borderRadius: '50%',
                      background: `${config.color}18`, border: `2px solid ${config.color}`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                      <Icon size={10} color={config.color} />
                    </div>

                    {/* Content */}
                    <div style={{ flex: 1, background: '#fff', border: `1px solid ${C.border}`, borderRadius: 10, padding: '12px 14px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div style={{ fontSize: 12, fontWeight: 600, color: C.text }}>{config.label}</div>
                        {step.created_at && (
                          <div style={{ fontSize: 9, color: C.mutedLight, fontFamily: 'monospace' }}>
                            {serverDate(step.created_at).toLocaleTimeString()}
                          </div>
                        )}
                      </div>
                      {step.actor_id && (
                        <div style={{ fontSize: 10, color: C.muted, marginTop: 3 }}>
                          by <span style={{ fontWeight: 600 }}>{step.actor_id}</span>
                        </div>
                      )}
                      {Object.keys(details).length > 0 && (
                        <div style={{ marginTop: 6, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                          {Object.entries(details).map(([key, val]) => (
                            <span key={key} style={{
                              fontSize: 9, padding: '2px 8px', borderRadius: 4,
                              background: '#FFFFFF', border: `1px solid ${C.border}`,
                              color: C.textSub, fontFamily: 'monospace',
                            }}>
                              {key}: {typeof val === 'number' ? val.toFixed(1) : String(val)}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
