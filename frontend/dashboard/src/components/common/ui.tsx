import type { CSSProperties, ReactNode, ButtonHTMLAttributes } from 'react'

// ── Design tokens ─────────────────────────────────────────────────────────────
export const C = {
  primary:    '#0284C7',
  blue:       '#2563EB',
  red:        '#EF4444',
  amber:      '#F59E0B',
  green:      '#10B981',
  muted:      '#64748B',
  mutedLight: '#94A3B8',
  border:     '#E2E8F0',
  bg:         '#F8FAFC',
  card:       '#FFFFFF',
  text:       '#0F172A',
  textSub:    '#475569',
} as const

// ── StatusPill ────────────────────────────────────────────────────────────────
const STATUS_CONFIG = {
  approved: { label: 'Auto-Approved',      bg: '#F0FDF4', color: '#059669', border: '#BBF7D0' },
  review:   { label: 'Moderator Review',   bg: '#FFFBEB', color: '#D97706', border: '#FDE68A' },
  siu:      { label: 'SIU Investigation',  bg: '#FFF5F5', color: '#DC2626', border: '#FECACA' },
  active:   { label: 'Active',             bg: '#F0FDF4', color: '#059669', border: '#BBF7D0' },
  draft:    { label: 'Draft',              bg: '#F8FAFC', color: '#64748B', border: '#E2E8F0' },
  final:    { label: 'Final',              bg: '#EFF6FF', color: '#2563EB', border: '#BFDBFE' },
  open:     { label: 'Open',              bg: '#FFF5F5', color: '#DC2626', border: '#FECACA' },
  closed:   { label: 'Closed',            bg: '#F0FDF4', color: '#059669', border: '#BBF7D0' },
  pending:  { label: 'Pending',           bg: '#FFFBEB', color: '#D97706', border: '#FDE68A' },
  processing: { label: 'Processing',      bg: '#EFF6FF', color: '#2563EB', border: '#BFDBFE' },
  rejected: { label: 'Rejected',          bg: '#FFF5F5', color: '#DC2626', border: '#FECACA' },
  moderator_approved: { label: 'Approved (Moderator)', bg: '#F0FDF4', color: '#059669', border: '#BBF7D0' },
  confirmed_fraud: { label: 'Fraud Confirmed', bg: '#FFF5F5', color: '#DC2626', border: '#FECACA' },
  cleared:  { label: 'Cleared (SIU)',     bg: '#F0FDF4', color: '#059669', border: '#BBF7D0' },
} as const

type StatusKey = keyof typeof STATUS_CONFIG

export function StatusPill({ status, size = 'sm' }: { status: StatusKey; size?: 'xs' | 'sm' }) {
  const cfg = STATUS_CONFIG[status]
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}`,
      borderRadius: 20, padding: size === 'xs' ? '1px 7px' : '3px 10px',
      fontSize: size === 'xs' ? 10 : 11, fontWeight: 600,
      whiteSpace: 'nowrap' as const,
    }}>
      <span style={{ width: 5, height: 5, borderRadius: '50%', background: cfg.color, display: 'inline-block', flexShrink: 0 }} />
      {cfg.label}
    </span>
  )
}

// ── RiskBadge ─────────────────────────────────────────────────────────────────
export function RiskBadge({ score }: { score: number }) {
  const color = score < 15 ? C.green : score <= 85 ? C.amber : C.red
  return (
    <span style={{
      fontSize: 11, fontWeight: 700, color,
      background: `${color}18`, border: `1px solid ${color}44`,
      borderRadius: 5, padding: '2px 7px', whiteSpace: 'nowrap' as const,
      fontFamily: 'monospace',
    }}>
      {score}%
    </span>
  )
}

// ── Card ──────────────────────────────────────────────────────────────────────
export function Card({ children, style, accent }: { children: ReactNode; style?: CSSProperties; accent?: string }) {
  return (
    <div style={{
      background: '#fff', border: `1px solid ${accent ?? C.border}`,
      borderRadius: 10, ...style,
    }}>
      {children}
    </div>
  )
}

// ── Btn ───────────────────────────────────────────────────────────────────────
type BtnVariant = 'primary' | 'danger' | 'success' | 'outline' | 'ghost'

interface BtnProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: BtnVariant
  size?: 'sm' | 'md'
  children: ReactNode
  fullWidth?: boolean
}

const BTN_STYLES: Record<BtnVariant, CSSProperties> = {
  primary: { background: C.blue,  color: '#fff', border: 'none' },
  danger:  { background: C.red,   color: '#fff', border: 'none' },
  success: { background: C.green, color: '#fff', border: 'none' },
  outline: { background: '#fff',  color: C.textSub, border: `1px solid ${C.border}` },
  ghost:   { background: 'transparent', color: C.muted, border: 'none' },
}

export function Btn({ variant = 'primary', size = 'md', children, fullWidth, style, disabled, ...rest }: BtnProps) {
  return (
    <button
      {...rest}
      disabled={disabled}
      style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6,
        padding: size === 'sm' ? '7px 12px' : '11px 16px',
        borderRadius: 8, fontSize: size === 'sm' ? 12 : 13, fontWeight: 700,
        fontFamily: 'Inter, system-ui, sans-serif', cursor: disabled ? 'not-allowed' : 'pointer',
        width: fullWidth ? '100%' : undefined,
        opacity: disabled ? 0.45 : 1, transition: 'opacity 0.15s',
        ...BTN_STYLES[variant],
        ...style,
      }}
    >
      {children}
    </button>
  )
}

// ── FormInput ─────────────────────────────────────────────────────────────────
interface InputProps {
  label: string
  placeholder?: string
  value: string
  onChange: (v: string) => void
  type?: string
  multiline?: boolean
  rows?: number
  required?: boolean
  hint?: string
  dark?: boolean
}

export function FormInput({ label, placeholder, value, onChange, type = 'text', multiline, rows = 3, required, hint, dark }: InputProps) {
  const baseStyle: CSSProperties = {
    width: '100%', boxSizing: 'border-box',
    padding: '9px 12px', fontSize: 14, borderRadius: 8,
    fontFamily: 'Inter, system-ui, sans-serif',
    outline: 'none', transition: 'border-color 0.15s',
    background: dark ? 'rgba(255,255,255,0.06)' : '#F8FAFC',
    border: dark ? '1px solid rgba(255,255,255,0.12)' : `1px solid ${C.border}`,
    color: dark ? '#E8EDF5' : C.text,
  }
  return (
    <div>
      <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 5, color: dark ? 'rgba(255,255,255,0.7)' : C.textSub }}>
        {label}{required && <span style={{ color: C.red, marginLeft: 2 }}>*</span>}
      </label>
      {multiline
        ? <textarea rows={rows} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} style={{ ...baseStyle, resize: 'vertical' }} />
        : <input type={type} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} style={baseStyle} />
      }
      {hint && <div style={{ fontSize: 10, color: dark ? 'rgba(255,255,255,0.35)' : C.mutedLight, marginTop: 4 }}>{hint}</div>}
    </div>
  )
}

// ── Section heading ───────────────────────────────────────────────────────────
export function SectionHeading({ children }: { children: ReactNode }) {
  return (
    <div style={{ fontSize: 10, fontWeight: 700, color: C.mutedLight, textTransform: 'uppercase' as const, letterSpacing: '0.06em', marginBottom: 8 }}>
      {children}
    </div>
  )
}

// ── Divider ───────────────────────────────────────────────────────────────────
export function Divider({ style }: { style?: CSSProperties }) {
  return <div style={{ height: 1, background: C.border, ...style }} />
}
