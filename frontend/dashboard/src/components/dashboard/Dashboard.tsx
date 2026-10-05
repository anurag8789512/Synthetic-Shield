import { useState, useEffect, useRef } from 'react'
import { Shield, Bell, Search, ChevronDown, Plug, LogOut, Cable, KeyRound, BookOpen, Activity, Network } from 'lucide-react'
import { C } from '../common/ui'
import { fetchAllClaims } from '../../data/api'
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

const ROLE_LABELS: Record<string, string> = {
  senior: 'Senior Claims Adjuster',
  siu_officer: 'SIU Officer',
  moderator: 'Claims Moderator',
}

function initialsOf(name: string): string {
  const parts = name.replace(/\./g, '').trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

export default function Dashboard({ role = 'senior', onLogout }: { role?: string; onLogout?: () => void }) {
  const [tab, setTab] = useState<Tab>('queue')
  const [notifOpen, setNotifOpen] = useState(false)
  const [notifCount, setNotifCount] = useState(0)
  const [notifications, setNotifications] = useState<LiveNotif[]>([])
  const [search, setSearch] = useState('')
  const [mcpOpen, setMcpOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const mcpRef = useRef<HTMLDivElement>(null)
  const profileRef = useRef<HTMLDivElement>(null)
  const isLead = role === 'senior'

  // close header dropdowns on outside click
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (mcpRef.current && !mcpRef.current.contains(e.target as Node)) setMcpOpen(false)
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) setProfileOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const officerName = sessionStorage.getItem('ss_officer_name') || 'Officer'
  const officerRole = sessionStorage.getItem('ss_officer_role') || role
  const officerRoleLabel = ROLE_LABELS[officerRole] || officerRole

  // Fetch live notifications from claims
  useEffect(() => {
    const load = async () => {
      try {
        const claims = await fetchAllClaims()
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
              background: tab === t.id ? '#F9EEF1' : 'transparent',
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
              background: notifOpen ? '#F9EEF1' : '#fff',
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
                  style={{ padding: '10px 14px', borderBottom: i < notifications.length - 1 ? `1px solid #FFFFFF` : 'none', display: 'flex', gap: 10, cursor: 'pointer', transition: 'background 0.1s' }}
                  onMouseEnter={e => (e.currentTarget.style.background = '#FFFFFF')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                >
                  <div style={{ width: 6, height: 6, background: n.dot, borderRadius: '50%', marginTop: 4, flexShrink: 0 }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 11, color: '#2E2E2E', lineHeight: 1.4 }}>{n.text}</div>
                    <div style={{ fontSize: 9, color: C.mutedLight, marginTop: 2 }}>{n.time}</div>
                  </div>
                  <div style={{ fontSize: 9, color: C.blue, fontWeight: 600, alignSelf: 'center' }}>View →</div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* MCP Server — external-system connectivity (demo menu; options go live with the MCP rollout) */}
        <div ref={mcpRef} style={{ position: 'relative' }}>
          <button
            onClick={() => { setMcpOpen(v => !v); setProfileOpen(false) }}
            title="MCP Server — connect external insurance systems"
            style={{
              height: 34, borderRadius: 8, border: `1px solid ${mcpOpen ? C.blue : C.border}`,
              background: mcpOpen ? '#F9EEF1' : '#fff', display: 'flex', alignItems: 'center',
              gap: 6, padding: '0 10px', cursor: 'pointer',
            }}
          >
            <Plug size={14} color={mcpOpen ? C.blue : C.muted} />
            <span style={{ fontSize: 11, fontWeight: 700, color: mcpOpen ? C.blue : C.muted }}>MCP</span>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: C.green }} />
          </button>
          {mcpOpen && (
            <div style={{ position: 'absolute', top: 42, right: 0, width: 280, background: '#fff', border: `1px solid ${C.border}`, borderRadius: 10, boxShadow: '0 8px 24px rgba(0,0,0,0.1)', zIndex: 200, overflow: 'hidden' }}>
              <div style={{ padding: '10px 14px', borderBottom: `1px solid ${C.border}` }}>
                <div style={{ fontSize: 12, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Plug size={12} color={C.blue} /> MCP Server
                </div>
                <div style={{ fontSize: 9.5, color: C.mutedLight, marginTop: 3, lineHeight: 1.4 }}>
                  Connect external insurance systems and AI agents to SyntheticShield via the Model Context Protocol.
                </div>
              </div>
              <div style={{ padding: '8px 14px', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: 10, color: C.textSub, fontFamily: 'monospace' }}>http://localhost:8000/mcp</span>
                <span style={{ fontSize: 9, fontWeight: 700, color: C.green, display: 'flex', alignItems: 'center', gap: 4 }}>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: C.green }} /> READY
                </span>
              </div>
              {([
                [Network, 'Connected Systems', '0 external systems linked'],
                [Cable, 'Tool Catalog', 'submit_claim · score_breakdown · evidence'],
                [KeyRound, 'API Keys & Access', 'Manage partner credentials'],
                [Activity, 'Connection Logs', 'Tool-call audit history'],
                [BookOpen, 'Integration Guide', 'Connect Guidewire, Duck Creek & agents'],
              ] as const).map(([Icon, label, hint]) => (
                <div
                  key={label}
                  onClick={() => setMcpOpen(false)}
                  style={{ padding: '9px 14px', display: 'flex', gap: 10, alignItems: 'center', cursor: 'pointer', transition: 'background 0.1s' }}
                  onMouseEnter={e => (e.currentTarget.style.background = '#FFFFFF')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                >
                  <Icon size={13} color={C.muted} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: C.text }}>{label}</div>
                    <div style={{ fontSize: 9, color: C.mutedLight, marginTop: 1 }}>{hint}</div>
                  </div>
                  <span style={{ fontSize: 8, fontWeight: 700, color: '#D97706', background: '#FFFBEB', border: '1px solid #FDE68A', borderRadius: 4, padding: '1px 5px' }}>SOON</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Profile */}
        <div ref={profileRef} style={{ position: 'relative' }}>
          <div
            onClick={() => { setProfileOpen(v => !v); setMcpOpen(false) }}
            style={{ display: 'flex', alignItems: 'center', gap: 8, background: profileOpen ? '#F9EEF1' : C.bg, border: `1px solid ${profileOpen ? C.blue : C.border}`, borderRadius: 8, padding: '5px 10px 5px 6px', cursor: 'pointer' }}
          >
            <div style={{ width: 24, height: 24, borderRadius: 6, background: C.blue, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 9, fontWeight: 800, color: '#fff' }}>{initialsOf(officerName)}</div>
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: C.text, lineHeight: 1 }}>{officerName}</div>
              <div style={{ fontSize: 9, color: C.mutedLight, lineHeight: 1, marginTop: 2 }}>{officerRoleLabel}</div>
            </div>
            <ChevronDown size={11} color={C.mutedLight} style={{ transform: profileOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }} />
          </div>
          {profileOpen && (
            <div style={{ position: 'absolute', top: 42, right: 0, width: 200, background: '#fff', border: `1px solid ${C.border}`, borderRadius: 10, boxShadow: '0 8px 24px rgba(0,0,0,0.1)', zIndex: 200, overflow: 'hidden' }}>
              <div style={{ padding: '10px 14px', borderBottom: `1px solid ${C.border}` }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: C.text }}>{officerName}</div>
                <div style={{ fontSize: 9, color: C.mutedLight, marginTop: 2 }}>{officerRoleLabel}</div>
              </div>
              <div
                onClick={() => { setProfileOpen(false); onLogout?.() }}
                style={{ padding: '10px 14px', display: 'flex', gap: 9, alignItems: 'center', cursor: 'pointer', transition: 'background 0.1s' }}
                onMouseEnter={e => (e.currentTarget.style.background = '#FFF5F5')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                <LogOut size={13} color={C.red} />
                <span style={{ fontSize: 11, fontWeight: 600, color: C.red }}>Log out</span>
              </div>
            </div>
          )}
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
