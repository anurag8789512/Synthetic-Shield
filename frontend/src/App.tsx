import { useState } from 'react'
import MobilePortal from './components/mobile/MobilePortal'
import Dashboard from './components/dashboard/Dashboard'
import DashboardLogin from './components/dashboard/DashboardLogin'

export default function App() {
  const [view, setView] = useState<'dashboard' | 'mobile'>('dashboard')
  const [authenticated, setAuthenticated] = useState(false)
  const [officerRole, setOfficerRole] = useState('')

  return (
    <div style={{ minHeight: '100vh', background: '#0B0F17' }}>
      {/* View switcher */}
      <div style={{
        position: 'fixed', top: 12, left: '50%', transform: 'translateX(-50%)',
        zIndex: 9999, background: 'rgba(13,17,27,0.9)', backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)', border: '1px solid rgba(255,255,255,0.1)',
        borderRadius: 40, padding: '3px', display: 'flex', gap: 3,
      }}>
        {(['dashboard', 'mobile'] as const).map(v => (
          <button key={v} onClick={() => setView(v)} style={{
            padding: '6px 16px', borderRadius: 36, border: 'none', cursor: 'pointer',
            fontSize: 11, fontWeight: 700, fontFamily: 'Inter, system-ui, sans-serif',
            letterSpacing: '0.03em', transition: 'all 0.2s',
            background: view === v ? 'rgba(37,99,235,0.9)' : 'transparent',
            color: view === v ? '#fff' : 'rgba(255,255,255,0.4)',
          }}>
            {v === 'dashboard' ? 'SIU Dashboard' : 'Mobile FNOL'}
          </button>
        ))}
      </div>

      {view === 'dashboard'
        ? (authenticated ? <Dashboard role={officerRole} /> : <DashboardLogin onLogin={(role) => { setOfficerRole(role); setAuthenticated(true) }} />)
        : <MobilePortal />
      }
    </div>
  )
}
