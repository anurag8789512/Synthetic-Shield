import { useState, useEffect, useRef } from 'react'
import {
  Shield, ChevronRight, ChevronLeft, Phone, Mail, ArrowLeft,
  Car, Calendar, CheckCircle, Upload, Mic, FileText, Film, Camera,
  AlertTriangle, Clock, RotateCcw, X, Loader,
  Wifi, Battery, Signal,
} from 'lucide-react'
import { Btn, FormInput, C } from '../common/ui'

// ── Live policy data ──────────────────────────────────────────────────────────────
interface CoverageInfo { id: number; label: string; type: string; limitCents: number | null }
interface PolicyInfo {
  id: number
  policyNumber: string
  status: string
  renewalDate: string
  coverages: CoverageInfo[]
}

function usePolicy() {
  const [policy, setPolicy] = useState<PolicyInfo | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const token = sessionStorage.getItem('ss_token')
    if (!token) { setError('Not authenticated.'); return }
    fetch('http://localhost:8000/policies/me', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : Promise.reject())
      .then((list: any[]) => {
        const p = list?.[0]
        if (!p) { setError('No policy found for this account.'); return }
        setPolicy({
          id: p.id,
          policyNumber: p.policy_number,
          status: p.status,
          renewalDate: p.renewal_date || '',
          coverages: (p.coverages || []).map((c: any) => ({
            id: c.id,
            label: c.coverage_label,
            type: c.coverage_type,
            limitCents: c.coverage_limit_cents,
          })),
        })
      })
      .catch(() => setError('Could not load your policy. Is the backend running?'))
  }, [])

  return { policy, error }
}

const fmtLimit = (cents: number | null) =>
  cents == null ? '' : `Coverage limit ${(cents / 100).toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })}`

const fmtDate = (iso: string) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' }) : '—'

// Convert a recorded blob (webm/opus) to 16-bit PCM WAV — required by the audio detection vendor
async function blobToWavFile(blob: Blob): Promise<File> {
  const arrayBuffer = await blob.arrayBuffer()
  const ctx = new AudioContext()
  const audioBuf = await ctx.decodeAudioData(arrayBuffer)
  await ctx.close()

  const numCh = Math.min(audioBuf.numberOfChannels, 2)
  const dataLen = audioBuf.length * numCh * 2
  const buffer = new ArrayBuffer(44 + dataLen)
  const view = new DataView(buffer)
  const writeStr = (off: number, s: string) => { for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i)) }

  writeStr(0, 'RIFF'); view.setUint32(4, 36 + dataLen, true); writeStr(8, 'WAVE')
  writeStr(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true)
  view.setUint16(22, numCh, true); view.setUint32(24, audioBuf.sampleRate, true)
  view.setUint32(28, audioBuf.sampleRate * numCh * 2, true); view.setUint16(32, numCh * 2, true)
  view.setUint16(34, 16, true); writeStr(36, 'data'); view.setUint32(40, dataLen, true)

  const channels = Array.from({ length: numCh }, (_, ch) => audioBuf.getChannelData(ch))
  let offset = 44
  for (let i = 0; i < audioBuf.length; i++) {
    for (let ch = 0; ch < numCh; ch++) {
      const s = Math.max(-1, Math.min(1, channels[ch][i]))
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true)
      offset += 2
    }
  }
  return new File([buffer], 'voice_statement.wav', { type: 'audio/wav' })
}

// ── Screen types ──────────────────────────────────────────────────────────────
type Screen = 'login' | 'otp' | 'policy' | 'claim' | 'verifying' | 'outcome' | 'confirmation' | 'reappeal'
type Outcome = 'approved' | 'review' | 'siu'
type ClaimStep = 0 | 1 | 2 | 3 | 4 | 5 // A B C D E F

// ── Waveform animation bars ───────────────────────────────────────────────────
function WaveBars({ active }: { active: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 2, height: 36 }}>
      {Array.from({ length: 24 }).map((_, i) => (
        <div key={i} style={{
          width: 3, borderRadius: 2, flexShrink: 0,
          background: active ? 'linear-gradient(to top,#0284C7,#38BDF8)' : 'rgba(255,255,255,0.15)',
          animationName: active ? 'wave-bar' : 'none',
          animationDuration: `${0.6 + (i % 5) * 0.09}s`,
          animationDelay: `${(i * 0.06).toFixed(2)}s`,
          animationTimingFunction: 'ease-in-out',
          animationIterationCount: 'infinite',
          animationDirection: 'alternate',
          height: active ? undefined : '4px',
          minHeight: 4,
        }} />
      ))}
    </div>
  )
}

// ── Progress bar ──────────────────────────────────────────────────────────────
const STEP_LABELS = ['Coverage', 'Video', 'Photos', 'Statement', 'Documents', 'Review']
function StepProgress({ step }: { step: ClaimStep }) {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        {STEP_LABELS.map((l, i) => (
          <div key={i} style={{ textAlign: 'center', flex: 1 }}>
            <div style={{
              width: 22, height: 22, borderRadius: '50%', margin: '0 auto 4px',
              background: i < step ? C.primary : i === step ? C.blue : 'rgba(255,255,255,0.1)',
              border: `2px solid ${i <= step ? C.primary : 'rgba(255,255,255,0.15)'}`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              {i < step
                ? <CheckCircle size={10} color="#fff" />
                : <span style={{ fontSize: 9, fontWeight: 700, color: i === step ? '#fff' : 'rgba(255,255,255,0.35)' }}>{i + 1}</span>
              }
            </div>
            <div style={{ fontSize: 8, color: i === step ? '#7DD3FC' : 'rgba(255,255,255,0.3)', fontWeight: i === step ? 700 : 400 }}>
              {l}
            </div>
          </div>
        ))}
      </div>
      <div style={{ height: 2, background: 'rgba(255,255,255,0.1)', borderRadius: 1, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${(step / 5) * 100}%`, background: `linear-gradient(90deg,${C.primary},#38BDF8)`, borderRadius: 1, transition: 'width 0.4s' }} />
      </div>
    </div>
  )
}

// ── Phone frame wrapper ───────────────────────────────────────────────────────
function PhoneFrame({ children, dark = true }: { children: React.ReactNode; dark?: boolean }) {
  return (
    <div style={{
      width: 393, minHeight: 852, background: dark ? '#0B1221' : '#F8FAFC',
      borderRadius: 48, overflow: 'hidden',
      boxShadow: '0 0 0 1px rgba(255,255,255,0.08), 0 40px 80px rgba(0,0,0,0.6)',
      display: 'flex', flexDirection: 'column', position: 'relative',
    }}>
      {/* Status bar */}
      <div style={{ background: dark ? '#0B1221' : '#fff', padding: '14px 24px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: dark ? '#fff' : '#0F172A', fontFamily: 'Inter,system-ui,sans-serif' }}>9:41</span>
        <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
          <Signal size={12} color={dark ? 'rgba(255,255,255,0.7)' : '#475569'} />
          <Wifi size={12} color={dark ? 'rgba(255,255,255,0.7)' : '#475569'} />
          <Battery size={12} color={dark ? 'rgba(255,255,255,0.7)' : '#475569'} />
        </div>
      </div>
      {children}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Screen 1 — Login
// ═══════════════════════════════════════════════════════════════════════════════
function LoginScreen({ onNext }: { onNext: (identifier: string, debugOtp: string | null) => void }) {
  const [method, setMethod] = useState<'phone' | 'email'>('phone')
  const [value, setValue] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const send = async () => {
    if (!value) return
    setError('')
    setLoading(true)
    try {
      const res = await fetch('http://localhost:8000/auth/request-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ identifier: value }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail || 'Failed to send OTP')
        setLoading(false)
        return
      }
      setLoading(false)
      onNext(value, data.debug_otp || null)
    } catch {
      setError('Cannot reach server. Is the backend running?')
      setLoading(false)
    }
  }

  // Pre-fill hint for demo
  const placeholder = method === 'phone' ? '6202234696' : 'krishnaanurag16@gmail.com'

  return (
    <PhoneFrame>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: '0 28px 48px' }}>
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <div style={{ width: 60, height: 60, borderRadius: 18, background: 'linear-gradient(135deg,#0284C7,#2563EB)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px', boxShadow: '0 0 30px rgba(2,132,199,0.35)' }}>
            <Shield size={28} color="#fff" />
          </div>
          <div style={{ fontSize: 22, fontWeight: 800, color: '#fff', fontFamily: 'Inter,system-ui,sans-serif' }}>SyntheticShield</div>
          <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', marginTop: 4 }}>Motor Insurance Claims Portal</div>
        </div>

        <div style={{ fontSize: 20, fontWeight: 700, color: '#fff', textAlign: 'center', marginBottom: 6 }}>Sign in to your account</div>
        <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.4)', textAlign: 'center', marginBottom: 28 }}>Access your policy and submit claims</div>

        {/* Toggle */}
        <div style={{ display: 'flex', background: 'rgba(255,255,255,0.06)', borderRadius: 10, padding: 3, marginBottom: 18 }}>
          {(['phone', 'email'] as const).map(m => (
            <button key={m} onClick={() => setMethod(m)} style={{
              flex: 1, padding: '9px', borderRadius: 8, border: 'none', cursor: 'pointer',
              background: method === m ? '#0284C7' : 'transparent',
              color: method === m ? '#fff' : 'rgba(255,255,255,0.45)',
              fontSize: 13, fontWeight: 600, fontFamily: 'Inter,system-ui,sans-serif',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
              transition: 'all 0.2s',
            }}>
              {m === 'phone' ? <Phone size={14} /> : <Mail size={14} />}
              {m === 'phone' ? 'Phone Number' : 'Email Address'}
            </button>
          ))}
        </div>

        {/* Input */}
        <FormInput
          dark
          label={method === 'phone' ? 'Mobile Number' : 'Email Address'}
          placeholder={placeholder}
          value={value}
          onChange={setValue}
          type={method === 'phone' ? 'tel' : 'email'}
          required
        />

        <div style={{ marginTop: 20 }}>
          <Btn fullWidth variant="primary" onClick={send} disabled={!value || loading} style={{ background: 'linear-gradient(135deg,#0284C7,#2563EB)', fontSize: 15, padding: '14px' }}>
            {loading ? <><Loader size={16} style={{ animation: 'spin-slow 1s linear infinite' }} /> Sending…</> : 'Send Verification Code'}
          </Btn>
        </div>

        {error && (
          <div style={{ marginTop: 12, background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 8, padding: '8px 12px', fontSize: 12, color: '#FCA5A5', textAlign: 'center' }}>
            {error}
          </div>
        )}

        <div style={{ marginTop: 20, textAlign: 'center', fontSize: 11, color: 'rgba(255,255,255,0.25)' }}>
          By continuing you agree to our Terms of Service and Privacy Policy
        </div>
      </div>
    </PhoneFrame>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Screen 2 — OTP Verification
// ═══════════════════════════════════════════════════════════════════════════════
function OTPScreen({ onNext, onBack, identifier, debugOtp }: { onNext: () => void; onBack: () => void; identifier: string; debugOtp: string | null }) {
  const [digits, setDigits] = useState<string[]>(['', '', '', '', '', ''])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [countdown, setCountdown] = useState(30)
  const refs = Array.from({ length: 6 }, () => useRef<HTMLInputElement>(null))

  useEffect(() => {
    const t = setInterval(() => setCountdown(c => c > 0 ? c - 1 : 0), 1000)
    return () => clearInterval(t)
  }, [])

  const verifyCode = async (code: string) => {
    setLoading(true)
    setError('')
    try {
      const res = await fetch('http://localhost:8000/auth/verify-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ identifier, code }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail || 'Verification failed')
        setLoading(false)
        return
      }
      // Store session token for later API calls
      sessionStorage.setItem('ss_token', data.session_token)
      sessionStorage.setItem('ss_user', data.full_name)
      setLoading(false)
      onNext()
    } catch {
      setError('Cannot reach server.')
      setLoading(false)
    }
  }

  const handleDigit = (i: number, val: string) => {
    const d = val.replace(/\D/g, '').slice(-1)
    const next = [...digits]
    next[i] = d
    setDigits(next)
    if (d && i < 5) refs[i + 1].current?.focus()
    if (next.every(x => x !== '') && d) {
      verifyCode(next.join(''))
    }
  }

  const handleKey = (i: number, e: React.KeyboardEvent) => {
    if (e.key === 'Backspace' && !digits[i] && i > 0) refs[i - 1].current?.focus()
  }

  return (
    <PhoneFrame>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: '0 28px 48px' }}>
        <button onClick={onBack} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.5)', display: 'flex', alignItems: 'center', gap: 6, marginBottom: 32, padding: 0, fontSize: 13 }}>
          <ArrowLeft size={16} /> Back
        </button>

        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{ width: 56, height: 56, borderRadius: 16, background: 'rgba(2,132,199,0.15)', border: '1px solid rgba(2,132,199,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
            <Phone size={24} color="#0284C7" />
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, color: '#fff', marginBottom: 6 }}>Verify your identity</div>
          <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.4)' }}>Enter the 6-digit code we sent to your number</div>
        </div>

        {/* 6 digit boxes */}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginBottom: 28 }}>
          {digits.map((d, i) => (
            <input
              key={i}
              ref={refs[i]}
              value={d}
              onChange={e => handleDigit(i, e.target.value)}
              onKeyDown={e => handleKey(i, e)}
              maxLength={1}
              inputMode="numeric"
              style={{
                width: 46, height: 54, textAlign: 'center', fontSize: 22, fontWeight: 700,
                background: d ? 'rgba(2,132,199,0.15)' : 'rgba(255,255,255,0.06)',
                border: `2px solid ${d ? '#0284C7' : 'rgba(255,255,255,0.12)'}`,
                borderRadius: 10, color: '#fff', outline: 'none',
                fontFamily: 'monospace', transition: 'border-color 0.2s',
              }}
            />
          ))}
        </div>

        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          {countdown > 0
            ? <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.35)' }}>Resend code in <strong style={{ color: 'rgba(255,255,255,0.6)' }}>{countdown}s</strong></span>
            : <button onClick={() => setCountdown(30)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#0284C7', fontSize: 13, fontWeight: 600 }}>Resend Code</button>
          }
        </div>

        <Btn fullWidth variant="primary" onClick={() => verifyCode(digits.join(''))} disabled={loading || digits.some(d => !d)} style={{ background: 'linear-gradient(135deg,#0284C7,#2563EB)', fontSize: 15, padding: '14px' }}>
          {loading ? <><Loader size={16} style={{ animation: 'spin-slow 1s linear infinite' }} /> Verifying…</> : 'Verify Code'}
        </Btn>

        {error && (
          <div style={{ marginTop: 12, background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 8, padding: '8px 12px', fontSize: 12, color: '#FCA5A5', textAlign: 'center' }}>
            {error}
          </div>
        )}

        {debugOtp && (
          <div style={{ marginTop: 16, textAlign: 'center', fontSize: 12, background: 'rgba(2,132,199,0.15)', border: '1px solid rgba(2,132,199,0.3)', borderRadius: 8, padding: '8px 12px', color: '#7DD3FC' }}>
            Demo OTP: <strong style={{ letterSpacing: '0.15em' }}>{debugOtp}</strong>
          </div>
        )}
      </div>
    </PhoneFrame>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Screen 3 — Policy Dashboard
// ═══════════════════════════════════════════════════════════════════════════════
function PolicyDashboard({ onSubmitClaim }: { onSubmitClaim: () => void }) {
  const { policy, error } = usePolicy()
  const holderName = sessionStorage.getItem('ss_user') || 'Policyholder'

  if (!policy) {
    return (
      <PhoneFrame dark={false}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12, padding: '0 28px' }}>
          {error
            ? <div style={{ background: '#FEF2F2', border: '1px solid #FECACA', borderRadius: 10, padding: '12px 16px', fontSize: 13, color: '#B91C1C', textAlign: 'center' }}>{error}</div>
            : <><Loader size={22} color="#0284C7" style={{ animation: 'spin-slow 1s linear infinite' }} /><div style={{ fontSize: 13, color: '#64748B' }}>Loading your policy…</div></>
          }
        </div>
      </PhoneFrame>
    )
  }

  return (
    <PhoneFrame dark={false}>
      {/* Header */}
      <div style={{ background: '#0B1221', padding: '12px 20px 18px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 32, height: 32, borderRadius: 9, background: 'linear-gradient(135deg,#0284C7,#2563EB)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Shield size={16} color="#fff" />
            </div>
            <div>
              <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', letterSpacing: '0.06em', textTransform: 'uppercase' as const }}>SyntheticShield</div>
              <div style={{ fontSize: 15, fontWeight: 700, color: '#fff' }}>{holderName}</div>
            </div>
          </div>
          <span style={{
            background: policy.status === 'active' ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)',
            border: `1px solid ${policy.status === 'active' ? 'rgba(16,185,129,0.35)' : 'rgba(239,68,68,0.35)'}`,
            color: policy.status === 'active' ? '#6EE7B7' : '#FCA5A5',
            borderRadius: 20, padding: '3px 10px', fontSize: 10, fontWeight: 700,
          }}>
            ● {policy.status.toUpperCase()}
          </span>
        </div>
        <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.35)', marginBottom: 2 }}>Policy Number</div>
        <div style={{ fontSize: 13, fontFamily: 'monospace', color: '#7DD3FC', letterSpacing: '0.04em' }}>{policy.policyNumber}</div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* Coverages */}
        <div style={{ background: '#fff', borderRadius: 12, padding: '14px', border: '1px solid #E2E8F0' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <div style={{ width: 32, height: 32, borderRadius: 8, background: '#EFF6FF', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Car size={16} color="#2563EB" />
            </div>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#0F172A' }}>Active Coverages</div>
          </div>
          {policy.coverages.map((cov, i) => (
            <div key={cov.id} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', paddingBottom: i < policy.coverages.length - 1 ? 10 : 0, marginBottom: i < policy.coverages.length - 1 ? 10 : 0, borderBottom: i < policy.coverages.length - 1 ? '1px solid #F1F5F9' : 'none' }}>
              <CheckCircle size={14} color="#10B981" style={{ marginTop: 1, flexShrink: 0 }} />
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: '#0F172A' }}>{cov.label}</div>
                {cov.limitCents != null && <div style={{ fontSize: 10, color: '#64748B', marginTop: 2 }}>{fmtLimit(cov.limitCents)}</div>}
              </div>
            </div>
          ))}
        </div>

        {/* Renewal */}
        <div style={{ background: '#fff', borderRadius: 12, padding: '14px', border: '1px solid #E2E8F0', display: 'flex', gap: 8, alignItems: 'center' }}>
          <Calendar size={16} color="#2563EB" />
          <div>
            <div style={{ fontSize: 10, color: '#94A3B8' }}>Renewal Date</div>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#0F172A' }}>{fmtDate(policy.renewalDate)}</div>
          </div>
        </div>
      </div>

      {/* CTA */}
      <div style={{ padding: '12px 16px 24px', background: '#fff', borderTop: '1px solid #E2E8F0', flexShrink: 0 }}>
        <button onClick={onSubmitClaim} style={{
          width: '100%', padding: '15px', borderRadius: 12, border: 'none', cursor: 'pointer',
          background: 'linear-gradient(135deg,#0284C7,#2563EB)', color: '#fff',
          fontSize: 15, fontWeight: 700, fontFamily: 'Inter,system-ui,sans-serif',
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
          boxShadow: '0 4px 18px rgba(2,132,199,0.35)',
        }}>
          Submit a Claim <ChevronRight size={18} />
        </button>
      </div>
    </PhoneFrame>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Screen 4 — Claim Submission (Steps A–E)
// ═══════════════════════════════════════════════════════════════════════════════
function ClaimSubmission({ onSubmit, onBack }: { onSubmit: (claimDbId: number, claimNumber: string) => void; onBack: () => void }) {
  const [step, setStep] = useState<ClaimStep>(0)
  const [coverage, setCoverage] = useState('')
  const [location, setLocation] = useState('')
  const [description, setDescription] = useState('')
  const [claimAmount, setClaimAmount] = useState('')
  const [videoUploadState, setVideoUploadState] = useState<'idle' | 'uploading' | 'done'>('idle')
  const [videoFile, setVideoFile] = useState<File | null>(null)
  const [imageUploadState, setImageUploadState] = useState<'idle' | 'uploading' | 'done'>('idle')
  const [imageFiles, setImageFiles] = useState<File[]>([])
  const [recordState, setRecordState] = useState<'idle' | 'recording' | 'done'>('idle')
  const [recordSecs, setRecordSecs] = useState(0)
  const [recordError, setRecordError] = useState('')
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null)
  const [audioPlaybackUrl, setAudioPlaybackUrl] = useState('')
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const [pdfState, setPdfState] = useState<'idle' | 'error' | 'done'>('idle')
  const [pdfName, setPdfName] = useState('')
  const [pdfFile, setPdfFile] = useState<File | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const videoInputRef = useRef<HTMLInputElement>(null)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const pdfInputRef = useRef<HTMLInputElement>(null)
  const { policy } = usePolicy()
  const coverages = policy?.coverages ?? []

  const canNext =
    step === 0 ? !!coverage && !!location && !!description && Number(claimAmount) > 0 :
    step === 1 ? videoUploadState === 'done' :
    step === 2 ? imageUploadState === 'done' :
    step === 3 ? recordState === 'done' :
    true // steps D and E always can proceed

  const toggleRecord = async () => {
    if (recordState === 'idle') {
      setRecordError('')
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        const recorder = new MediaRecorder(stream)
        audioChunksRef.current = []
        recorder.ondataavailable = e => { if (e.data.size > 0) audioChunksRef.current.push(e.data) }
        recorder.onstop = () => {
          const blob = new Blob(audioChunksRef.current, { type: recorder.mimeType || 'audio/webm' })
          setAudioBlob(blob)
          setAudioPlaybackUrl(URL.createObjectURL(blob))
          stream.getTracks().forEach(t => t.stop())
        }
        mediaRecorderRef.current = recorder
        recorder.start()
        setRecordState('recording')
        timerRef.current = setInterval(() => setRecordSecs(s => s + 1), 1000)
      } catch {
        setRecordError('Microphone access denied. Please allow microphone permission to record your statement.')
      }
    } else if (recordState === 'recording') {
      clearInterval(timerRef.current!)
      mediaRecorderRef.current?.stop()
      setRecordState('done')
    }
  }

  const resetRecording = () => {
    if (audioPlaybackUrl) URL.revokeObjectURL(audioPlaybackUrl)
    setAudioBlob(null)
    setAudioPlaybackUrl('')
    setRecordState('idle')
    setRecordSecs(0)
  }

  useEffect(() => () => clearInterval(timerRef.current!), [])

  const fmt = (s: number) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`

  const handlePdfDrop = (name: string) => {
    if (!name.toLowerCase().endsWith('.pdf')) { setPdfState('error'); return }
    setPdfState('done'); setPdfName(name)
  }

  const handleVideoSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setVideoFile(file)
      setVideoUploadState('uploading')
      setTimeout(() => setVideoUploadState('done'), 1200)
    }
  }

  const handleImageSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    if (files.length > 0) {
      setImageFiles(files)
      setImageUploadState('uploading')
      setTimeout(() => setImageUploadState('done'), 1200)
    }
  }

  const handlePdfSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.pdf')) { setPdfState('error'); return }
    setPdfFile(file)
    setPdfState('done')
    setPdfName(file.name)
  }

  const submitToBackend = async () => {
    setSubmitting(true)
    const token = sessionStorage.getItem('ss_token')
    const formData = new FormData()
    formData.append('coverage_id', coverage)
    formData.append('accident_location', location)
    formData.append('accident_description', description)
    formData.append('claim_amount', claimAmount)

    if (videoFile) {
      formData.append('video', videoFile)
    }

    if (imageFiles.length > 0) {
      formData.append('image', imageFiles[0])
    }

    // Real recorded audio statement, converted to WAV for vendor analysis
    if (audioBlob) {
      try {
        formData.append('audio', await blobToWavFile(audioBlob))
      } catch {
        formData.append('audio', new File([audioBlob], 'voice_statement.webm', { type: audioBlob.type }))
      }
    }

    // Optional PDF
    if (pdfFile) {
      formData.append('document', pdfFile)
    }

    try {
      const res = await fetch('http://localhost:8000/claims', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData,
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Submission failed')
      setSubmitting(false)
      onSubmit(data.claim_id, data.claim_number)
    } catch (e: any) {
      setSubmitting(false)
      setSubmitError(e.message || 'Could not reach the server. Is the backend running?')
    }
  }

  const goNext = () => { if (step < 5) setStep((step + 1) as ClaimStep); else submitToBackend() }
  const goPrev = () => { if (step > 0) setStep((step - 1) as ClaimStep); else onBack() }

  return (
    <PhoneFrame dark={false}>
      {/* Header */}
      <div style={{ background: '#0B1221', padding: '10px 16px 16px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <button onClick={goPrev} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.5)', padding: 0 }}>
            <ChevronLeft size={20} />
          </button>
          <div style={{ fontSize: 15, fontWeight: 700, color: '#fff' }}>New Claim</div>
        </div>
        <StepProgress step={step} />
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '18px 16px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: '#0284C7', textTransform: 'uppercase' as const, letterSpacing: '0.07em' }}>
          Step {String.fromCharCode(65 + step)} — {STEP_LABELS[step]}
        </div>

        {/* ── Step A: Coverage & Incident ── */}
        {step === 0 && (
          <>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 5, color: '#475569' }}>
                What would you like to claim under? <span style={{ color: '#EF4444' }}>*</span>
              </label>
              <select value={coverage} onChange={e => setCoverage(e.target.value)} style={{
                width: '100%', padding: '9px 12px', fontSize: 14, borderRadius: 8,
                border: '1px solid #E2E8F0', background: '#F8FAFC', color: coverage ? '#0F172A' : '#94A3B8',
                outline: 'none', fontFamily: 'Inter,system-ui,sans-serif', appearance: 'none' as const,
              }}>
                <option value="">Select coverage…</option>
                {coverages.map(c => <option key={c.id} value={String(c.id)}>{c.label}</option>)}
              </select>
            </div>
            <FormInput label="Accident Location" placeholder="e.g. 47 Main St, Sydney NSW" value={location} onChange={setLocation} required />
            <FormInput label="Description of incident" placeholder="Briefly describe what happened…" value={description} onChange={setDescription} multiline rows={4} required />
            <FormInput
              label="Claim Amount"
              placeholder="e.g. 850"
              value={claimAmount}
              onChange={v => setClaimAmount(v.replace(/[^0-9.]/g, ''))}
              type="number"
              hint="Enter the amount you're claiming, in USD."
              required
            />
          </>
        )}

        {/* ── Step B: Video upload ── */}
        {step === 1 && (
          <>
            <div style={{ background: '#EFF6FF', border: '1px solid #BFDBFE', borderRadius: 10, padding: '10px 14px', display: 'flex', gap: 8 }}>
              <Film size={14} color="#2563EB" style={{ flexShrink: 0, marginTop: 1 }} />
              <span style={{ fontSize: 11, color: '#1E40AF', lineHeight: 1.5 }}>
                <strong>Required:</strong> Upload a video of the damage (dashcam footage, walkthrough, etc.). This will be scanned by SyntheticShield AI for deepfake artifacts.
              </span>
            </div>

            <input
              ref={videoInputRef}
              type="file"
              accept="video/*"
              style={{ display: 'none' }}
              onChange={handleVideoSelect}
            />
            <div
              onClick={videoUploadState === 'idle' ? () => videoInputRef.current?.click() : undefined}
              style={{
                borderRadius: 14, border: `2px dashed ${videoUploadState === 'done' ? '#10B981' : '#BFDBFE'}`,
                background: videoUploadState === 'done' ? 'rgba(16,185,129,0.04)' : '#fff',
                padding: '28px 20px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10,
                cursor: videoUploadState === 'idle' ? 'pointer' : 'default',
              }}
            >
              {videoUploadState === 'uploading' && (
                <>
                  <Loader size={28} color="#0284C7" style={{ animation: 'spin-slow 1s linear infinite' }} />
                  <span style={{ fontSize: 13, fontWeight: 600, color: '#0284C7' }}>Processing video…</span>
                </>
              )}
              {videoUploadState === 'done' && videoFile && (
                <>
                  <CheckCircle size={28} color="#10B981" />
                  <span style={{ fontSize: 13, fontWeight: 600, color: '#10B981' }}>Video selected</span>
                  <span style={{ fontSize: 11, color: '#64748B' }}>{videoFile.name}</span>
                </>
              )}
              {videoUploadState === 'idle' && (
                <>
                  <div style={{ width: 48, height: 48, borderRadius: 14, background: '#EFF6FF', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Film size={22} color="#2563EB" />
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A' }}>Tap to upload video evidence</div>
                    <div style={{ fontSize: 11, color: '#64748B', marginTop: 3 }}>MP4, MOV, AVI, WebM · Max 500MB</div>
                  </div>
                </>
              )}
            </div>
          </>
        )}

        {/* ── Step C: Image upload ── */}
        {step === 2 && (
          <>
            <div style={{ background: '#EFF6FF', border: '1px solid #BFDBFE', borderRadius: 10, padding: '10px 14px', display: 'flex', gap: 8 }}>
              <Camera size={14} color="#2563EB" style={{ flexShrink: 0, marginTop: 1 }} />
              <span style={{ fontSize: 11, color: '#1E40AF', lineHeight: 1.5 }}>
                <strong>Required:</strong> Upload photos of the damage. These will be scanned by SyntheticShield AI for synthetic image detection.
              </span>
            </div>

            <input
              ref={imageInputRef}
              type="file"
              accept="image/*"
              multiple
              style={{ display: 'none' }}
              onChange={handleImageSelect}
            />
            <div
              onClick={imageUploadState === 'idle' ? () => imageInputRef.current?.click() : undefined}
              style={{
                borderRadius: 14, border: `2px dashed ${imageUploadState === 'done' ? '#10B981' : '#BFDBFE'}`,
                background: imageUploadState === 'done' ? 'rgba(16,185,129,0.04)' : '#fff',
                padding: '28px 20px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10,
                cursor: imageUploadState === 'idle' ? 'pointer' : 'default',
              }}
            >
              {imageUploadState === 'uploading' && (
                <>
                  <Loader size={28} color="#0284C7" style={{ animation: 'spin-slow 1s linear infinite' }} />
                  <span style={{ fontSize: 13, fontWeight: 600, color: '#0284C7' }}>Processing photos…</span>
                </>
              )}
              {imageUploadState === 'done' && (
                <>
                  <CheckCircle size={28} color="#10B981" />
                  <span style={{ fontSize: 13, fontWeight: 600, color: '#10B981' }}>{imageFiles.length} photo{imageFiles.length > 1 ? 's' : ''} selected</span>
                  <span style={{ fontSize: 11, color: '#64748B' }}>{imageFiles.map(f => f.name).join(' · ')}</span>
                </>
              )}
              {imageUploadState === 'idle' && (
                <>
                  <div style={{ width: 48, height: 48, borderRadius: 14, background: '#EFF6FF', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Camera size={22} color="#2563EB" />
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A' }}>Tap to upload damage photos</div>
                    <div style={{ fontSize: 11, color: '#64748B', marginTop: 3 }}>JPG, PNG, HEIC · Multiple allowed</div>
                  </div>
                </>
              )}
            </div>
          </>
        )}

        {/* ── Step D: Voice Recording (mandatory) ── */}
        {step === 3 && (
          <>
            <div style={{ background: '#EFF6FF', border: '1px solid #BFDBFE', borderRadius: 10, padding: '10px 14px', display: 'flex', gap: 8 }}>
              <Mic size={14} color="#2563EB" style={{ flexShrink: 0, marginTop: 1 }} />
              <span style={{ fontSize: 11, color: '#1E40AF', lineHeight: 1.5 }}>
                <strong>Required:</strong> Record a voice statement describing the incident in your own words.
              </span>
            </div>

            <div style={{ background: '#0B1221', borderRadius: 14, padding: '16px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
              <div style={{ width: '100%' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <span style={{ fontSize: 9, fontFamily: 'monospace', color: '#38BDF8', letterSpacing: '0.1em' }}>VOICE ANALYSIS · LIVE</span>
                  {recordState === 'recording' && <span style={{ fontSize: 10, fontFamily: 'monospace', color: '#EF4444' }}>{fmt(recordSecs)}</span>}
                  {recordState === 'done' && <span style={{ fontSize: 10, fontFamily: 'monospace', color: '#10B981' }}>{fmt(recordSecs)} recorded</span>}
                </div>
                <WaveBars active={recordState === 'recording'} />
              </div>

              {/* Record / playback button */}
              <div style={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                {recordState === 'recording' && (
                  <div className="ring-expand" style={{ position: 'absolute', width: 72, height: 72, borderRadius: '50%', border: '1.5px solid rgba(239,68,68,0.5)', pointerEvents: 'none' }} />
                )}
                <button
                  onClick={recordState !== 'done' ? toggleRecord : undefined}
                  style={{
                    width: 68, height: 68, borderRadius: '50%', border: 'none', cursor: recordState === 'done' ? 'default' : 'pointer',
                    background: recordState === 'done' ? 'linear-gradient(135deg,#059669,#10B981)' : recordState === 'recording' ? 'linear-gradient(135deg,#DC2626,#EF4444)' : 'linear-gradient(135deg,#0284C7,#2563EB)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}
                >
                  {recordState === 'done' ? <CheckCircle size={26} color="#fff" /> : recordState === 'recording' ? <div style={{ width: 20, height: 20, background: '#fff', borderRadius: 3 }} /> : <Mic size={26} color="#fff" />}
                </button>
              </div>

              <div style={{ color: 'rgba(255,255,255,0.55)', fontSize: 12, textAlign: 'center' }}>
                {recordState === 'idle' ? 'Tap to start recording' : recordState === 'recording' ? 'Recording — tap to stop' : 'Statement captured'}
              </div>
            </div>

            {recordError && (
              <div style={{ background: '#FEF2F2', border: '1px solid #FECACA', borderRadius: 10, padding: '10px 14px', fontSize: 12, color: '#B91C1C' }}>
                {recordError}
              </div>
            )}

            {recordState === 'done' && (
              <div style={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 12, padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                {audioPlaybackUrl && <audio controls src={audioPlaybackUrl} style={{ width: '100%', height: 36 }} />}
                <button onClick={resetRecording} style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'none', border: 'none', cursor: 'pointer', color: '#64748B', fontSize: 12, alignSelf: 'flex-end' }}>
                  <RotateCcw size={12} /> Re-record
                </button>
              </div>
            )}
          </>
        )}

        {/* ── Step E: PDF (optional) ── */}
        {step === 4 && (
          <>
            <div style={{ background: '#FFFBEB', border: '1px solid #FDE68A', borderRadius: 10, padding: '10px 14px', display: 'flex', gap: 8 }}>
              <FileText size={14} color="#D97706" style={{ flexShrink: 0, marginTop: 1 }} />
              <span style={{ fontSize: 11, color: '#92400E', lineHeight: 1.5 }}>
                <strong>Optional:</strong> Upload a supporting document (police report, repair quote, etc.). PDF files only. You may skip this step.
              </span>
            </div>

            <input
              ref={pdfInputRef}
              type="file"
              accept=".pdf,application/pdf"
              style={{ display: 'none' }}
              onChange={handlePdfSelect}
            />
            <div
              onDragOver={e => e.preventDefault()}
              onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) { setPdfFile(f); handlePdfDrop(f.name) } }}
              onClick={() => pdfState === 'idle' ? pdfInputRef.current?.click() : undefined}
              style={{
                borderRadius: 14, border: `2px dashed ${pdfState === 'done' ? '#10B981' : pdfState === 'error' ? '#EF4444' : '#E2E8F0'}`,
                background: pdfState === 'done' ? 'rgba(16,185,129,0.04)' : pdfState === 'error' ? 'rgba(239,68,68,0.04)' : '#fff',
                padding: '24px 20px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, cursor: 'pointer',
              }}
            >
              {pdfState === 'done' && <><CheckCircle size={28} color="#10B981" /><span style={{ fontSize: 13, fontWeight: 600, color: '#10B981' }}>{pdfName}</span></>}
              {pdfState === 'error' && (
                <>
                  <X size={28} color="#EF4444" />
                  <span style={{ fontSize: 13, fontWeight: 600, color: '#EF4444' }}>Invalid file type</span>
                  <span style={{ fontSize: 11, color: '#64748B' }}>Only PDF files are accepted. Please try again.</span>
                </>
              )}
              {pdfState === 'idle' && (
                <>
                  <div style={{ width: 44, height: 44, borderRadius: 12, background: '#F8FAFC', border: '1px solid #E2E8F0', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <FileText size={20} color="#64748B" />
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 14, fontWeight: 600, color: '#0F172A' }}>Tap to upload PDF</div>
                    <div style={{ fontSize: 11, color: '#64748B', marginTop: 3 }}>PDF only · Police report, repair quote, etc.</div>
                  </div>
                </>
              )}
            </div>
          </>
        )}

        {/* ── Step F: Review & Submit ── */}
        {step === 5 && (
          <>
            <div style={{ fontSize: 15, fontWeight: 700, color: '#0F172A' }}>Review your claim</div>
            {[
              { label: 'Coverage', value: coverage },
              { label: 'Location', value: location },
              { label: 'Description', value: description },
              { label: 'Claim Amount', value: claimAmount ? `$${Number(claimAmount).toLocaleString()}` : '' },
              { label: 'Video', value: videoUploadState === 'done' && videoFile ? `${videoFile.name} ✓` : 'None' },
              { label: 'Photos', value: imageUploadState === 'done' ? `${imageFiles.length} photo${imageFiles.length > 1 ? 's' : ''} ✓` : 'None' },
              { label: 'Voice Statement', value: recordState === 'done' ? `${fmt(recordSecs)} recorded ✓` : 'None' },
              { label: 'Supporting Doc', value: pdfState === 'done' ? pdfName : 'Skipped (optional)' },
            ].map(({ label, value }) => (
              <div key={label} style={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 10, padding: '12px 14px' }}>
                <div style={{ fontSize: 10, fontWeight: 600, color: '#94A3B8', textTransform: 'uppercase' as const, letterSpacing: '0.06em', marginBottom: 4 }}>{label}</div>
                <div style={{ fontSize: 13, color: '#0F172A', lineHeight: 1.5 }}>{value || '—'}</div>
              </div>
            ))}
          </>
        )}
      </div>

      {/* Bottom nav */}
      <div style={{ padding: '12px 16px 24px', background: '#fff', borderTop: '1px solid #E2E8F0', display: 'flex', gap: 10, flexShrink: 0 }}>
        {step > 0 && (
          <Btn variant="outline" onClick={goPrev} style={{ flex: 1 }}>Back</Btn>
        )}
        {/* Only the Documents step (4) is optional — the voice statement (3) is
            mandatory server-side, so Skip must never bypass it. */}
        {step === 4 && (
          <Btn variant="ghost" onClick={goNext} style={{ flex: 1, color: '#64748B' }}>Skip</Btn>
        )}
        <Btn
          variant="primary"
          onClick={goNext}
          disabled={!canNext || submitting}
          style={{ flex: 2, background: 'linear-gradient(135deg,#0284C7,#2563EB)', fontSize: 14, padding: '13px' }}
        >
          {submitting ? <><Loader size={15} style={{ animation: 'spin-slow 1s linear infinite' }} /> Submitting…</> : step === 5 ? 'Submit Claim' : 'Continue'} {step < 5 && !submitting && <ChevronRight size={15} />}
        </Btn>
        {submitError && (
          <div style={{ marginTop: 8, background: '#FEF2F2', border: '1px solid #FECACA', borderRadius: 8, padding: '8px 12px', fontSize: 12, color: '#B91C1C', textAlign: 'center' }}>
            {submitError}
          </div>
        )}
      </div>
    </PhoneFrame>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Screen 5 — AI Verification (polls real claim status)
// ═══════════════════════════════════════════════════════════════════════════════
const STATUS_TO_OUTCOME: Record<string, Outcome> = {
  auto_approved: 'approved',
  moderator_review: 'review',
  siu_investigation: 'siu',
  siu_confirmed_fraud: 'siu',
  siu_cleared: 'approved',
  rejected: 'review',
}

function AIVerifying({ claimDbId, onDone }: { claimDbId: number; onDone: (o: Outcome) => void }) {
  const [progress, setProgress] = useState([0, 0, 0])

  useEffect(() => {
    const timers = [
      setTimeout(() => setProgress([100, 0, 0]), 600),
      setTimeout(() => setProgress([100, 100, 0]), 1500),
      setTimeout(() => setProgress([100, 100, 100]), 2600),
    ]

    // Poll the backend until AI analysis resolves the claim status
    // (real vendor analysis can take a few minutes)
    const token = sessionStorage.getItem('ss_token')
    let attempts = 0
    const poll = setInterval(async () => {
      attempts++
      try {
        const res = await fetch(`http://localhost:8000/claims/${claimDbId}`, { headers: { Authorization: `Bearer ${token}` } })
        if (res.ok) {
          const data = await res.json()
          if (data.status && data.status !== 'processing') {
            clearInterval(poll)
            onDone(STATUS_TO_OUTCOME[data.status] ?? 'review')
            return
          }
        }
      } catch { /* retry on next tick */ }
      if (attempts >= 150) {
        clearInterval(poll)
        onDone('review')
      }
    }, 2000)

    return () => { timers.forEach(clearTimeout); clearInterval(poll) }
  }, [claimDbId])

  const checks = [
    { label: 'Frame-level diffusion analysis', done: progress[0] === 100 },
    { label: 'Voice biometric verification',   done: progress[1] === 100 },
    { label: 'EXIF & metadata validation',      done: progress[2] === 100 },
  ]

  return (
    <PhoneFrame>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '0 28px' }}>
        {/* Pulsing shield */}
        <div style={{ position: 'relative', marginBottom: 32 }}>
          <div className="ring-expand" style={{ position: 'absolute', inset: -16, borderRadius: '50%', border: '1.5px solid rgba(2,132,199,0.4)' }} />
          <div className="ring-expand" style={{ position: 'absolute', inset: -16, borderRadius: '50%', border: '1.5px solid rgba(2,132,199,0.25)', animationDelay: '0.7s' }} />
          <div style={{ width: 80, height: 80, borderRadius: '50%', background: 'rgba(2,132,199,0.12)', border: '2px solid rgba(2,132,199,0.35)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div className="spin-slow" style={{ position: 'absolute', inset: 0, borderRadius: '50%', border: '2px solid transparent', borderTopColor: '#0284C7', borderRightColor: '#38BDF8' }} />
            <Shield size={32} color="#0284C7" />
          </div>
        </div>

        <div style={{ fontSize: 18, fontWeight: 700, color: '#fff', textAlign: 'center', marginBottom: 8 }}>
          Scanning Media for Authenticity…
        </div>
        <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', textAlign: 'center', lineHeight: 1.6, marginBottom: 32 }}>
          SyntheticShield AI is analysing your submission for deepfake and synthetic media artifacts
        </div>

        <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 12 }}>
          {checks.map((c, i) => (
            <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <div style={{ width: 20, height: 20, borderRadius: '50%', background: c.done ? 'rgba(16,185,129,0.2)' : 'rgba(255,255,255,0.06)', border: `1px solid ${c.done ? '#10B981' : 'rgba(255,255,255,0.1)'}`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                {c.done ? <CheckCircle size={11} color="#10B981" /> : <Loader size={11} color="rgba(255,255,255,0.3)" style={{ animation: 'spin-slow 1s linear infinite' }} />}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 11, color: c.done ? 'rgba(255,255,255,0.7)' : 'rgba(255,255,255,0.35)', marginBottom: 3 }}>{c.label}</div>
                <div style={{ height: 2, background: 'rgba(255,255,255,0.08)', borderRadius: 1, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: c.done ? '100%' : '0%', background: '#10B981', borderRadius: 1, transition: 'width 0.5s' }} />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </PhoneFrame>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Screen 6 — Outcome
// ═══════════════════════════════════════════════════════════════════════════════
function OutcomeScreen({ outcome, claimId, onContinue }: { outcome: Outcome; claimId: string; onContinue: () => void }) {
  const cfg = {
    approved: {
      icon: <CheckCircle size={40} color="#10B981" />,
      bg: '#F0FDF4', border: '#BBF7D0', title: 'Claim Approved',
      subtitle: 'Your claim has been automatically verified and approved.',
      detail: 'Your payout is being processed and will arrive within 2 business days.',
      color: '#059669',
    },
    review: {
      icon: <Clock size={40} color="#D97706" />,
      bg: '#FFFBEB', border: '#FDE68A', title: 'Under Moderator Review',
      subtitle: 'A claims officer will review your submission shortly.',
      detail: 'You\'ll be notified by SMS within 2 business hours.',
      color: '#D97706',
    },
    siu: {
      icon: <AlertTriangle size={40} color="#DC2626" />,
      bg: '#FFF5F5', border: '#FECACA', title: 'Claim Paused — Discrepancies Detected',
      subtitle: 'Our AI system identified potential issues with the submitted media.',
      detail: 'A SIU investigator will contact you within 1 business day to complete verification.',
      color: '#DC2626',
    },
  }[outcome]

  return (
    <PhoneFrame dark={false}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '0 24px' }}>
        <div style={{ width: '100%', background: cfg.bg, border: `1px solid ${cfg.border}`, borderRadius: 20, padding: '28px 24px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, textAlign: 'center' }}>
          {cfg.icon}
          <div style={{ fontSize: 20, fontWeight: 800, color: cfg.color }}>{cfg.title}</div>
          <div style={{ fontSize: 13, color: '#475569', lineHeight: 1.6 }}>{cfg.subtitle}</div>
          <div style={{ background: '#fff', border: `1px solid ${cfg.border}`, borderRadius: 10, padding: '10px 16px', width: '100%' }}>
            <div style={{ fontSize: 10, color: '#94A3B8', textTransform: 'uppercase' as const, letterSpacing: '0.06em', marginBottom: 3 }}>Claim Reference</div>
            <div style={{ fontSize: 15, fontFamily: 'monospace', fontWeight: 700, color: '#0F172A' }}>{claimId}</div>
          </div>
          <div style={{ fontSize: 12, color: cfg.color, background: `${cfg.border}55`, borderRadius: 8, padding: '8px 12px', lineHeight: 1.5 }}>{cfg.detail}</div>
        </div>
        <div style={{ marginTop: 24, width: '100%' }}>
          <Btn fullWidth variant="primary" onClick={onContinue} style={{ background: 'linear-gradient(135deg,#0284C7,#2563EB)', fontSize: 14, padding: '13px' }}>
            View Claim Status <ChevronRight size={15} />
          </Btn>
        </div>
      </div>
    </PhoneFrame>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Screen 7 — Confirmation
// ═══════════════════════════════════════════════════════════════════════════════
function ConfirmationScreen({ outcome, claimId, onHome, onReappeal }: { outcome: Outcome; claimId: string; onHome: () => void; onReappeal?: () => void }) {
  const statusLabel = outcome === 'approved' ? 'Auto-Approved' : outcome === 'review' ? 'Moderator Review' : 'SIU Investigation'
  const statusColor = outcome === 'approved' ? '#10B981' : outcome === 'review' ? '#D97706' : '#DC2626'
  const next = {
    approved: ['Your payout is being processed', 'You\'ll receive SMS confirmation shortly', 'Funds arrive within 2 business days'],
    review: ['A claims officer will review your submission', 'You\'ll be contacted within 2 business hours', 'You may be asked for additional information'],
    siu: ['A SIU investigator has been assigned', 'You\'ll be contacted within 1 business day', 'Do not alter or delete any submitted media'],
  }[outcome]

  return (
    <PhoneFrame dark={false}>
      <div style={{ background: '#0B1221', padding: '12px 20px 16px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 28, height: 28, borderRadius: 8, background: 'linear-gradient(135deg,#0284C7,#2563EB)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Shield size={14} color="#fff" />
          </div>
          <div style={{ fontSize: 14, fontWeight: 700, color: '#fff' }}>Claim Submitted</div>
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 16px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        {/* Claim number prominent */}
        <div style={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 14, padding: '20px', textAlign: 'center' }}>
          <div style={{ fontSize: 11, color: '#94A3B8', textTransform: 'uppercase' as const, letterSpacing: '0.06em', marginBottom: 6 }}>Your Claim Number</div>
          <div style={{ fontSize: 22, fontFamily: 'monospace', fontWeight: 800, color: '#0F172A', letterSpacing: '0.02em' }}>{claimId}</div>
          <div style={{ marginTop: 10 }}>
            <span style={{ background: `${statusColor}18`, border: `1px solid ${statusColor}44`, color: statusColor, borderRadius: 20, padding: '4px 12px', fontSize: 11, fontWeight: 700 }}>
              ● {statusLabel}
            </span>
          </div>
        </div>

        {/* What happens next */}
        <div style={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 12, padding: '14px' }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: '#0F172A', marginBottom: 12 }}>What happens next</div>
          {next.map((step, i) => (
            <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: i < next.length - 1 ? 10 : 0 }}>
              <div style={{ width: 20, height: 20, borderRadius: '50%', background: '#EFF6FF', border: '1px solid #BFDBFE', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <span style={{ fontSize: 9, fontWeight: 800, color: '#2563EB' }}>{i + 1}</span>
              </div>
              <span style={{ fontSize: 12, color: '#475569', lineHeight: 1.5, paddingTop: 2 }}>{step}</span>
            </div>
          ))}
        </div>

        {/* Info */}
        <div style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 10, padding: '12px 14px', fontSize: 11, color: '#64748B', lineHeight: 1.6 }}>
          Keep your claim number safe. You'll need it for any correspondence about this claim.
        </div>
      </div>

      <div style={{ padding: '12px 16px 24px', background: '#fff', borderTop: '1px solid #E2E8F0', flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {onReappeal && (
          <Btn fullWidth variant="primary" onClick={onReappeal} style={{ background: 'linear-gradient(135deg,#D97706,#F59E0B)', fontSize: 13, padding: '12px' }}>
            <AlertTriangle size={14} /> Appeal This Decision
          </Btn>
        )}
        <Btn fullWidth variant="outline" onClick={onHome}>Return to Policy Dashboard</Btn>
      </div>
    </PhoneFrame>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Screen 8 — Re-Appeal (after SIU rejection)
// ═══════════════════════════════════════════════════════════════════════════════
function ReAppealScreen({ claimId, onSubmit, onBack }: { claimId: string; onSubmit: () => void; onBack: () => void }) {
  const [reason, setReason] = useState<'new_evidence' | 'error_in_review' | 'partial_claim' | ''>('')
  const [explanation, setExplanation] = useState('')
  const [uploadState, setUploadState] = useState<'idle' | 'uploading' | 'done'>('idle')
  const [agreed, setAgreed] = useState(false)
  const [loading, setLoading] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  const canSubmit = !!reason && explanation.length >= 20 && agreed

  const handleSubmit = () => {
    setLoading(true)
    setTimeout(() => { setLoading(false); setSubmitted(true) }, 1600)
  }

  if (submitted) {
    return (
      <PhoneFrame dark={false}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '0 24px' }}>
          <div style={{ width: '100%', background: '#EFF6FF', border: '1px solid #BFDBFE', borderRadius: 20, padding: '28px 24px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, textAlign: 'center' }}>
            <div style={{ width: 56, height: 56, borderRadius: '50%', background: 'rgba(37,99,235,0.1)', border: '2px solid #2563EB', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <CheckCircle size={28} color="#2563EB" />
            </div>
            <div style={{ fontSize: 18, fontWeight: 800, color: '#1E40AF' }}>Appeal Submitted</div>
            <div style={{ fontSize: 13, color: '#475569', lineHeight: 1.6 }}>Your re-appeal for claim <strong>{claimId}</strong> has been submitted for review.</div>
            <div style={{ background: '#fff', border: '1px solid #BFDBFE', borderRadius: 10, padding: '12px 16px', width: '100%' }}>
              <div style={{ fontSize: 10, color: '#94A3B8', textTransform: 'uppercase' as const, letterSpacing: '0.06em', marginBottom: 3 }}>Expected Response</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: '#0F172A' }}>Within 3–5 business days</div>
            </div>
            <div style={{ fontSize: 12, color: '#2563EB', background: '#DBEAFE', borderRadius: 8, padding: '8px 12px', lineHeight: 1.5 }}>
              A senior reviewer will re-examine your case with the new information provided.
            </div>
          </div>
          <div style={{ marginTop: 24, width: '100%' }}>
            <Btn fullWidth variant="primary" onClick={onSubmit} style={{ background: 'linear-gradient(135deg,#0284C7,#2563EB)', fontSize: 14, padding: '13px' }}>
              Return to Policy Dashboard
            </Btn>
          </div>
        </div>
      </PhoneFrame>
    )
  }

  return (
    <PhoneFrame dark={false}>
      {/* Header */}
      <div style={{ background: '#0B1221', padding: '10px 16px 16px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
          <button onClick={onBack} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.5)', padding: 0 }}>
            <ChevronLeft size={20} />
          </button>
          <div style={{ fontSize: 15, fontWeight: 700, color: '#fff' }}>Appeal Claim Decision</div>
        </div>
        <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>Claim: <span style={{ color: '#7DD3FC', fontFamily: 'monospace' }}>{claimId}</span></div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '18px 16px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        {/* Warning banner */}
        <div style={{ background: '#FFFBEB', border: '1px solid #FDE68A', borderRadius: 10, padding: '10px 14px', display: 'flex', gap: 8 }}>
          <AlertTriangle size={14} color="#D97706" style={{ flexShrink: 0, marginTop: 1 }} />
          <span style={{ fontSize: 11, color: '#92400E', lineHeight: 1.5 }}>
            Your claim was flagged due to potential discrepancies. You may submit a re-appeal with additional evidence or clarification.
          </span>
        </div>

        {/* Reason for appeal */}
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 8, color: '#475569' }}>
            Reason for Appeal <span style={{ color: '#EF4444' }}>*</span>
          </label>
          {[
            { id: 'new_evidence' as const, label: 'I have new supporting evidence' },
            { id: 'error_in_review' as const, label: 'I believe there was an error in the review' },
            { id: 'partial_claim' as const, label: 'I want to submit a partial/modified claim' },
          ].map(opt => (
            <label key={opt.id} onClick={() => setReason(opt.id)} style={{
              display: 'flex', alignItems: 'center', gap: 10, padding: '11px 14px',
              background: reason === opt.id ? '#EFF6FF' : '#fff',
              border: `1px solid ${reason === opt.id ? '#2563EB' : '#E2E8F0'}`,
              borderRadius: 10, marginBottom: 8, cursor: 'pointer', transition: 'all 0.15s',
            }}>
              <div style={{
                width: 18, height: 18, borderRadius: '50%',
                border: `2px solid ${reason === opt.id ? '#2563EB' : '#CBD5E1'}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
              }}>
                {reason === opt.id && <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#2563EB' }} />}
              </div>
              <span style={{ fontSize: 13, color: '#0F172A', fontWeight: reason === opt.id ? 600 : 400 }}>{opt.label}</span>
            </label>
          ))}
        </div>

        {/* Explanation */}
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 6, color: '#475569' }}>
            Detailed Explanation <span style={{ color: '#EF4444' }}>*</span>
          </label>
          <textarea
            value={explanation}
            onChange={e => setExplanation(e.target.value)}
            placeholder="Please explain why you believe this decision should be reconsidered. Include any relevant details..."
            rows={5}
            style={{
              width: '100%', boxSizing: 'border-box', padding: '10px 12px',
              fontSize: 14, borderRadius: 8, border: `1px solid ${C.border}`,
              background: '#F8FAFC', color: '#0F172A', outline: 'none',
              fontFamily: 'Inter,system-ui,sans-serif', resize: 'none',
            }}
          />
          <div style={{ fontSize: 10, color: explanation.length >= 20 ? '#64748B' : '#EF4444', marginTop: 4 }}>
            {explanation.length}/20 minimum characters
          </div>
        </div>

        {/* Additional evidence upload */}
        <div
          onClick={uploadState === 'idle' ? () => { setUploadState('uploading'); setTimeout(() => setUploadState('done'), 1800) } : undefined}
          style={{
            borderRadius: 12, border: `2px dashed ${uploadState === 'done' ? '#10B981' : '#BFDBFE'}`,
            background: uploadState === 'done' ? 'rgba(16,185,129,0.04)' : '#fff',
            padding: '16px', display: 'flex', alignItems: 'center', gap: 12,
            cursor: uploadState === 'idle' ? 'pointer' : 'default',
          }}
        >
          {uploadState === 'uploading' && (
            <>
              <Loader size={20} color="#0284C7" style={{ animation: 'spin-slow 1s linear infinite', flexShrink: 0 }} />
              <span style={{ fontSize: 13, fontWeight: 600, color: '#0284C7' }}>Uploading…</span>
            </>
          )}
          {uploadState === 'done' && (
            <>
              <CheckCircle size={20} color="#10B981" style={{ flexShrink: 0 }} />
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: '#10B981' }}>Evidence attached</div>
              </div>
            </>
          )}
          {uploadState === 'idle' && (
            <>
              <Upload size={20} color="#2563EB" style={{ flexShrink: 0 }} />
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: '#0F172A' }}>Upload additional evidence</div>
                <div style={{ fontSize: 11, color: '#64748B' }}>Photos, videos, documents (optional)</div>
              </div>
            </>
          )}
        </div>

        {/* Agreement */}
        <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', cursor: 'pointer' }}>
          <input type="checkbox" checked={agreed} onChange={e => setAgreed(e.target.checked)} style={{ accentColor: '#2563EB', marginTop: 2, flexShrink: 0 }} />
          <span style={{ fontSize: 11, color: '#64748B', lineHeight: 1.5 }}>
            I declare that the information provided in this appeal is truthful and accurate. I understand that submitting false information may result in claim denial and further action.
          </span>
        </label>
      </div>

      {/* Bottom CTA */}
      <div style={{ padding: '12px 16px 24px', background: '#fff', borderTop: '1px solid #E2E8F0', flexShrink: 0 }}>
        <Btn
          fullWidth
          variant="primary"
          onClick={handleSubmit}
          disabled={!canSubmit || loading}
          style={{ background: 'linear-gradient(135deg,#0284C7,#2563EB)', fontSize: 14, padding: '13px' }}
        >
          {loading ? <><Loader size={15} style={{ animation: 'spin-slow 1s linear infinite' }} /> Submitting Appeal…</> : 'Submit Re-Appeal'}
        </Btn>
      </div>
    </PhoneFrame>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Main: MobilePortal — orchestrates all screens
// ═══════════════════════════════════════════════════════════════════════════════
export default function MobilePortal() {
  const [screen, setScreen] = useState<Screen>('login')
  const [outcome, setOutcome] = useState<Outcome>('review')
  const [claimDbId, setClaimDbId] = useState<number | null>(null)
  const [claimId, setClaimId] = useState('')
  const [loginIdentifier, setLoginIdentifier] = useState('')
  const [debugOtp, setDebugOtp] = useState<string | null>(null)

  const handleOutcome = (o: Outcome) => { setOutcome(o); setScreen('outcome') }

  const handleClaimSubmitted = (dbId: number, claimNumber: string) => {
    setClaimDbId(dbId)
    setClaimId(claimNumber)
    setScreen('verifying')
  }

  const handleLoginNext = (identifier: string, otp: string | null) => {
    setLoginIdentifier(identifier)
    setDebugOtp(otp)
    setScreen('otp')
  }

  const renderScreen = () => {
    switch (screen) {
      case 'login':         return <LoginScreen onNext={handleLoginNext} />
      case 'otp':           return <OTPScreen onNext={() => setScreen('policy')} onBack={() => setScreen('login')} identifier={loginIdentifier} debugOtp={debugOtp} />
      case 'policy':        return <PolicyDashboard onSubmitClaim={() => setScreen('claim')} />
      case 'claim':         return <ClaimSubmission onSubmit={handleClaimSubmitted} onBack={() => setScreen('policy')} />
      case 'verifying':     return claimDbId != null ? <AIVerifying claimDbId={claimDbId} onDone={handleOutcome} /> : <PolicyDashboard onSubmitClaim={() => setScreen('claim')} />
      case 'outcome':       return <OutcomeScreen outcome={outcome} claimId={claimId} onContinue={() => setScreen('confirmation')} />
      case 'confirmation':  return <ConfirmationScreen outcome={outcome} claimId={claimId} onHome={() => setScreen('policy')} onReappeal={outcome === 'siu' ? () => setScreen('reappeal') : undefined} />
      case 'reappeal':       return <ReAppealScreen claimId={claimId} onSubmit={() => setScreen('policy')} onBack={() => setScreen('confirmation')} />
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', background: 'linear-gradient(135deg,#0B0F17 0%,#111827 100%)', padding: '72px 16px 24px' }}>
      {renderScreen()}
    </div>
  )
}
