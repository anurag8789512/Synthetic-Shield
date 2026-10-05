import { useState } from 'react'
import { Shield, Lock, Mail, Eye, EyeOff, Loader } from 'lucide-react'
import { C, Btn } from '../common/ui'

export default function DashboardLogin({ onLogin }: { onLogin: (role: string) => void }) {
  const [email, setEmail] = useState('krishnaanurag16@gmail.com')
  const [password, setPassword] = useState('shield@123')
  const [showPw, setShowPw] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email || !password) { setError('Please fill in all fields'); return }
    setError('')
    setLoading(true)
    try {
      const res = await fetch('http://localhost:8000/auth/dashboard-login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Login failed'); setLoading(false); return }
      sessionStorage.setItem('ss_officer_token', data.session_token)
      sessionStorage.setItem('ss_officer_role', data.role)
      sessionStorage.setItem('ss_officer_name', data.name)
      setLoading(false)
      onLogin(data.role)
    } catch {
      setError('Cannot reach server.')
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#FFFFFF', fontFamily: 'Inter, system-ui, sans-serif' }}>
      <div style={{ width: 400, background: '#fff', borderRadius: 16, border: `1px solid ${C.border}`, boxShadow: '0 8px 32px rgba(0,0,0,0.06)', padding: '40px 36px' }}>
        {/* Logo & Title */}
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{ width: 52, height: 52, borderRadius: 14, background: C.blue, display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px', boxShadow: '0 4px 16px rgba(128,0,32,0.25)' }}>
            <Shield size={24} color="#fff" />
          </div>
          <div style={{ fontSize: 20, fontWeight: 800, color: C.text }}>SyntheticShield</div>
          <div style={{ fontSize: 11, color: C.mutedLight, marginTop: 4, letterSpacing: '0.06em', textTransform: 'uppercase' }}>SIU Fraud Intelligence Platform</div>
        </div>

        <div style={{ fontSize: 16, fontWeight: 700, color: C.text, textAlign: 'center', marginBottom: 4 }}>Sign in to your account</div>
        <div style={{ fontSize: 13, color: C.muted, textAlign: 'center', marginBottom: 28 }}>Enter your credentials to access the dashboard</div>

        <form onSubmit={handleSubmit}>
          {/* Email */}
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: C.textSub, marginBottom: 6 }}>Work Email</label>
            <div style={{ position: 'relative' }}>
              <Mail size={15} color={C.mutedLight} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)' }} />
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@insurancecorp.com"
                style={{
                  width: '100%', boxSizing: 'border-box', padding: '11px 12px 11px 38px',
                  fontSize: 14, borderRadius: 8, border: `1px solid ${C.border}`,
                  background: C.bg, color: C.text, outline: 'none', fontFamily: 'inherit',
                  transition: 'border-color 0.15s',
                }}
              />
            </div>
          </div>

          {/* Password */}
          <div style={{ marginBottom: 20 }}>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: C.textSub, marginBottom: 6 }}>Password</label>
            <div style={{ position: 'relative' }}>
              <Lock size={15} color={C.mutedLight} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)' }} />
              <input
                type={showPw ? 'text' : 'password'}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="Enter your password"
                style={{
                  width: '100%', boxSizing: 'border-box', padding: '11px 40px 11px 38px',
                  fontSize: 14, borderRadius: 8, border: `1px solid ${C.border}`,
                  background: C.bg, color: C.text, outline: 'none', fontFamily: 'inherit',
                  transition: 'border-color 0.15s',
                }}
              />
              <button type="button" onClick={() => setShowPw(v => !v)} style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
                {showPw ? <EyeOff size={15} color={C.mutedLight} /> : <Eye size={15} color={C.mutedLight} />}
              </button>
            </div>
          </div>

          {/* Remember + Forgot */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: C.muted, cursor: 'pointer' }}>
              <input type="checkbox" style={{ accentColor: C.blue }} />
              Remember me
            </label>
            <span style={{ fontSize: 12, color: C.blue, fontWeight: 600, cursor: 'pointer' }}>Forgot password?</span>
          </div>

          {error && (
            <div style={{ background: '#FFF5F5', border: '1px solid #FECACA', borderRadius: 8, padding: '8px 12px', marginBottom: 16, fontSize: 12, color: '#DC2626' }}>
              {error}
            </div>
          )}

          <Btn type="submit" fullWidth variant="primary" disabled={loading} style={{ fontSize: 14, padding: '13px' }}>
            {loading ? <><Loader size={15} style={{ animation: 'spin-slow 1s linear infinite' }} /> Signing in…</> : 'Sign In'}
          </Btn>
        </form>

        <div style={{ marginTop: 20, textAlign: 'center', fontSize: 11, color: C.mutedLight }}>
          Protected by enterprise SSO · Contact IT for access
        </div>
      </div>
    </div>
  )
}
