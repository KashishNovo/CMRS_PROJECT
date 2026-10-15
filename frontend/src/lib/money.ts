/**
 * Money helpers. Amounts travel as decimal strings; any arithmetic in the browser
 * (selected totals, live differences) is done in integer paise with BigInt so
 * 0.1 + 0.2 problems can't happen. The server re-computes everything anyway.
 */

const DECIMAL = /^-?\d+(\.\d{1,2})?$/

export function isValidAmount(value: string) {
  return DECIMAL.test(value.trim())
}

export function toPaise(value: string | null | undefined): bigint {
  if (!value) return 0n
  const v = value.trim()
  if (!DECIMAL.test(v)) return 0n
  const negative = v.startsWith('-')
  const [whole, frac = ''] = v.replace('-', '').split('.')
  const paise = BigInt(whole) * 100n + BigInt((frac + '00').slice(0, 2))
  return negative ? -paise : paise
}

export function fromPaise(paise: bigint): string {
  const negative = paise < 0n
  const abs = negative ? -paise : paise
  const whole = abs / 100n
  const frac = (abs % 100n).toString().padStart(2, '0')
  return `${negative ? '-' : ''}${whole}.${frac}`
}

export function sum(values: (string | null | undefined)[]): string {
  return fromPaise(values.reduce((acc, v) => acc + toPaise(v), 0n))
}

export function subtract(a: string, b: string): string {
  return fromPaise(toPaise(a) - toPaise(b))
}

export function compare(a: string, b: string): number {
  const d = toPaise(a) - toPaise(b)
  return d === 0n ? 0 : d > 0n ? 1 : -1
}

const formatter = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2 })
/** Indian short scale for chart axes: ₹25k, ₹1.2L, ₹3.4Cr. */
function compactInr(value: string) {
  const paise = toPaise(value)
  const rupees = Number(paise / 100n)
  const abs = Math.abs(rupees)
  const [div, unit] = abs >= 1e7 ? [1e7, 'Cr'] : abs >= 1e5 ? [1e5, 'L'] : abs >= 1e3 ? [1e3, 'k'] : [1, '']
  const n = rupees / div
  return `₹${Number.isInteger(n) ? n : n.toFixed(1).replace(/\.0$/, '')}${unit}`
}

/** "123456.5" -> "₹1,23,456.50" (Indian digit grouping). Display only. */
export function inr(value: string | null | undefined, opts: { compact?: boolean } = {}) {
  if (value === null || value === undefined || value === '') return '—'
  // Intl accepts decimal strings without converting through float (ES2023).
  const v = value as unknown as number
  return opts.compact ? compactInr(value) : formatter.format(v)
}

export function isZero(value: string | null | undefined) {
  return toPaise(value) === 0n
}
