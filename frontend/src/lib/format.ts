const dateFmt = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
const dateTimeFmt = new Intl.DateTimeFormat('en-IN', {
  day: 'numeric',
  month: 'short',
  hour: 'numeric',
  minute: '2-digit',
})
const timeFmt = new Intl.DateTimeFormat('en-IN', { hour: 'numeric', minute: '2-digit' })

export const fmtDate = (v?: string | null) => (v ? dateFmt.format(new Date(v.length === 10 ? v + 'T00:00:00' : v)) : '—')
export const fmtDateTime = (v?: string | null) => (v ? dateTimeFmt.format(new Date(v)) : '—')
export const fmtTime = (v?: string | null) => (v ? timeFmt.format(new Date(v)) : '—')

/** Local YYYY-MM-DD (not UTC) for date inputs and API filters. */
export function isoDate(d = new Date()) {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function monthStart(d = new Date()) {
  return isoDate(new Date(d.getFullYear(), d.getMonth(), 1))
}

export function daysAgo(n: number) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return isoDate(d)
}
