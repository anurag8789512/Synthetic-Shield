import { useState } from 'react'
import Dashboard from './components/dashboard/Dashboard'
import DashboardLogin from './components/dashboard/DashboardLogin'

export default function DashboardApp() {
  const [authenticated, setAuthenticated] = useState(false)
  const [officerRole, setOfficerRole] = useState('')

  const handleLogin = (role: string) => {
    setOfficerRole(role)
    setAuthenticated(true)
  }

  return (
    <div style={{ minHeight: '100vh', background: '#F8FAFC' }}>
      {authenticated ? <Dashboard role={officerRole} /> : <DashboardLogin onLogin={handleLogin} />}
    </div>
  )
}
