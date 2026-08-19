import { useState, useEffect } from 'react'
import { Shield, Bell, Search, ChevronDown } from 'lucide-react'
import { C } from '../common/ui'
import ClaimsQueue from './ClaimsQueue'
import Analytics from './Analytics'
import CaseFiles from './CaseFiles'
import Reports from './Reports'
import ClaimFlowchart from './ClaimFlowchart'
import Efficiency from './Efficiency'

type Tab = 'queue' | 'analytics' | 'cases' | 'reports' | 'lifecycle' | 'efficiency'

interface LiveNotif {
  text: string
  time: string
  dot: string
  claimId?: number
}

export default function Dashboard({ role = 'senior' }: { role?: string }) {
  const [tab, setTab] = useState<Tab>('queue')
  const [notifOpen, setNotifOpen] = useState(false)
  const [notifCount, setNotifCount] = useState(0)
  const [notifications, setNotifications] = useState<LiveNotif[]>([])
  const [search, setSearch] = useState('')
  const isLead = role === 'senior'

  // Fetch live notifications from claims
  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch('http://localhost:8000/claims/queue/all')
        if (!res.ok) return
        const claims = await res.json()
        const notifs: LiveNotif[] = claims.slice(0, 6).map((c: any) => {
          const score = c.fraud_confidence_score ?? 0
          const dot = score > 85 ? C.red : score > 15 ? C.amber : C.green
          const statusText = c.status === 'siu_investigation' ? 'flagged for SIU' :
            c.status === 'moderator_review' ? 'sent to moderator review' :
            c.status === 'auto_approved' ? 'auto-approved' : c.status.replace(/_/g, ' ')
          const created = c.created_at ? new Date(c.created_at) : new Date()
          const mins = Math.floor((Date.now() - created.getTime()) / 60000)
          const timeAgo = mins < 60 ? `${mins}m ago` : `${Math.floor(mins / 60)}h ago`
          return {
            text: `${c.claim_number} ${statusText}${score ? ` — ${score.toFixed(0)}% risk` : ''}`,
            time: timeAgo,
            dot,
            claimId: c.id,
          }
        })
        setNotifications(notifs)
        setNotifCount(notifs.length)
      } catch {}
    }
    load()
    const interval = setInterval(load, 8000)
    return () => clearInterval(interval)
  }, [])

  const tabs: { id: Tab; label: string }[] = [
    { id: 'queue',     label: 'Claims Queue' },
    { id: 'analytics', label: 'Analytics' },
    { id: 'cases',     label: 'Case Files' },
    { id: 'lifecycle', label: 'Lifecycle' },
    ...(isLead ? [{ id: 'efficiency' as Tab, label: 'Efficiency' }] : []),
    { id: 'reports',   label: 'Reports' },
  ]

  return (
    <div style={{ minHeight: '100vh', background: C.bg, display: 'flex', flexDirection: 'column', fontFamily: 'Inter, system-ui, sans-serif', color: C.text }}>

      {/* ── Top nav ──────────────────────────────────────────────────────────── */}
      <header style={{
        height: 56, background: '#fff', borderBottom: `1px solid ${C.border}`,
        display: 'flex', alignItems: 'center', padding: '0 20px', gap: 14,
        position: 'sticky', top: 0, zIndex: 100, flexShrink: 0,
      }}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          <div style={{ width: 30, height: 30, borderRadius: 8, background: C.blue, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Shield size={15} color="#fff" />
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: C.text, lineHeight: 1 }}>SyntheticShield</div>
            <div style={{ fontSize: 9, color: C.mutedLight, letterSpacing: '0.07em', textTransform: 'uppercase' as const }}>Fraud Intelligence</div>
          </div>
        </div>

        <div style={{ width: 1, height: 24, background: C.border, margin: '0 4px' }} />

        {/* Tabs */}
        <nav style={{ display: 'flex', gap: 2 }}>
          {tabs.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} style={{
              padding: '6px 14px', borderRadius: 6, border: 'none', cursor: 'pointer',
              background: tab === t.id ? '#EFF6FF' : 'transparent',
              color: tab === t.id ? C.blue : C.muted,
              fontSize: 12, fontWeight: tab === t.id ? 700 : 400,
              transition: 'all 0.15s',
            }}>{t.label}</button>
          ))}
        </nav>

        <div style={{ flex: 1 }} />

        {/* Search */}
        <div style={{ position: 'relative', width: 210 }}>
          <Search size={13} color={C.mutedLight} style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)' }} />
          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search claims, cases…"
            style={{
              width: '100%', height: 32, background: C.bg, border: `1px solid ${C.border}`,
              borderRadius: 7, color: C.text, fontSize: 12, padding: '0 10px 0 28px',
              outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' as const,
            }}
          />
        </div>

        {/* Notifications */}
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => { setNotifOpen(v => !v); setNotifCount(0) }}
            style={{
              width: 34, height: 34, borderRadius: 8, border: `1px solid ${C.border}`,
              background: notifOpen ? '#EFF6FF' : '#fff',
              display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', position: 'relative',
            }}
          >
            <Bell size={15} color={notifOpen ? C.blue : C.muted} />
            {notifCount > 0 && (
              <div style={{ position: 'absolute', top: -3, right: -3, width: 15, height: 15, background: C.red, borderRadius: '50%', border: '2px solid #fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 8, fontWeight: 800, color: '#fff' }}>
                {notifCount}
              </div>
            )}
          </button>
          {notifOpen && (
            <div style={{ position: 'absolute', top: 42, right: 0, width: 320, background: '#fff', border: `1px solid ${C.border}`, borderRadius: 10, boxShadow: '0 8px 24px rgba(0,0,0,0.1)', zIndex: 200, overflow: 'hidden' }}>
              <div style={{ padding: '10px 14px', borderBottom: `1px solid ${C.border}`, fontSize: 12, fontWeight: 700, display: 'flex', justifyContent: 'space-between' }}>
                <span>Notifications</span>
                {notifications.length > 0 && <span style={{ fontSize: 9, color: C.mutedLight }}>{notifications.length} claims</span>}
              </div>
              {notifications.length === 0 && (
                <div style={{ padding: '20px 14px', textAlign: 'center', fontSize: 11, color: C.mutedLight }}>No claims yet. Submit one from the mobile app.</div>
              )}
              {notifications.map((n, i) => (
                <div
                  key={i}
                  onClick={() => { setTab('queue'); setNotifOpen(false) }}
                  style={{ padding: '10px 14px', borderBottom: i < notifications.length - 1 ? `1px solid #F8FAFC` : 'none', display: 'flex', gap: 10, cursor: 'pointer', transition: 'background 0.1s' }}
                  onMouseEnter={e => (e.currentTarget.style.background = '#F8FAFC')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                >
                  <div style={{ width: 6, height: 6, background: n.dot, borderRadius: '50%', marginTop: 4, flexShrink: 0 }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 11, color: '#334155', lineHeight: 1.4 }}>{n.text}</div>
                    <div style={{ fontSize: 9, color: C.mutedLight, marginTop: 2 }}>{n.time}</div>
                  </div>
                  <div style={{ fontSize: 9, color: C.blue, fontWeight: 600, alignSelf: 'center' }}>View →</div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Profile */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8, padding: '5px 10px 5px 6px', cursor: 'pointer' }}>
          <div style={{ width: 24, height: 24, borderRadius: 6, background: C.blue, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 9, fontWeight: 800, color: '#fff' }}>KR</div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: C.text, lineHeight: 1 }}>K. Rodriguez</div>
            <div style={{ fontSize: 9, color: C.mutedLight, lineHeight: 1, marginTop: 2 }}>Senior Claims Adjuster</div>
          </div>
          <ChevronDown size={11} color={C.mutedLight} />
        </div>
      </header>

      {/* ── Tab content ──────────────────────────────────────────────────────── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0 }}>
        {tab === 'queue'     && <ClaimsQueue headerSearch={search} />}
        {tab === 'analytics' && <Analytics />}
        {tab === 'cases'     && <CaseFiles />}
        {tab === 'lifecycle' && <ClaimFlowchart />}
        {tab === 'efficiency' && isLead && <Efficiency />}
        {tab === 'reports'   && <Reports />}
      </div>
    </div>
  )
}
