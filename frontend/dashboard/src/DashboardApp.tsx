import { useState } from 'react'
import Dashboard from './components/dashboard/Dashboard'
import DashboardLogin from './components/dashboard/DashboardLogin'
import { logoutOfficer } from './data/api'

export default function DashboardApp() {
  const [authenticated, setAuthenticated] = useState(false)
  const [officerRole, setOfficerRole] = useState('')

  const handleLogin = (role: string) => {
    setOfficerRole(role)
    setAuthenticated(true)
  }

  const handleLogout = async () => {
    await logoutOfficer()
    setOfficerRole('')
    setAuthenticated(false)
  }

  return (
    <div style={{ minHeight: '100vh', background: '#F8FAFC' }}>
      {authenticated ? <Dashboard role={officerRole} onLogout={handleLogout} /> : <DashboardLogin onLogin={handleLogin} />}
    </div>
  )
}
