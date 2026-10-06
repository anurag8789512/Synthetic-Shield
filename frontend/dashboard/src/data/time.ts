// The backend stores naive UTC datetimes and serializes them without a zone
// ("2026-10-06T08:23:47"); `new Date()` would read those as local time. Treat any
// server timestamp without an explicit zone as UTC.
export function serverDate(value: string): Date {
  const hasZone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(value.trim())
  return new Date(hasZone ? value : `${value.trim().replace(' ', 'T')}Z`)
}

export function timeAgo(value: string | null | undefined): string {
  if (!value) return ''
  const mins = Math.max(0, Math.floor((Date.now() - serverDate(value).getTime()) / 60000))
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ${mins % 60}m ago`
  return `${Math.floor(hours / 24)}d ${hours % 24}h ago`
}
