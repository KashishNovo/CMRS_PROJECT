import { createContext, useCallback, useContext, useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { ApiError } from '../api/client'
import { inr } from '../lib/money'

/* ------------------------------------------------------------------ money */
export function Amount({ value, compact, className = '' }: { value: string | null | undefined; compact?: boolean; className?: string }) {
  return <span className={`amount ${className}`}>{inr(value, { compact })}</span>
}

/* ------------------------------------------------------------------ status chips: one colour per custody stage */
type Tone = 'agent' | 'count' | 'branch' | 'bank' | 'settled' | 'alert' | 'neutral'
const STATUS: Record<string, [Tone, string]> = {
  // collections
  COLLECTED: ['agent', 'With agent'],
  SUBMITTED: ['count', 'Awaiting count'],
  BRANCH_RECEIVED: ['branch', 'In branch'],
  DEPOSITED: ['bank', 'Deposited'],
  SETTLED: ['settled', 'Settled'],
  VOIDED: ['neutral', 'Voided'],
  // submissions
  PENDING: ['count', 'Awaiting count'],
  APPROVED: ['branch', 'Approved'],
  REJECTED: ['alert', 'Rejected'],
  // deposits
  PENDING_SETTLEMENT: ['bank', 'Awaiting credit'],
  SETTLEMENT_MISMATCH: ['alert', 'Credit mismatch'],
  FAILED: ['alert', 'Failed'],
  // discrepancies, loans, instalments
  OPEN: ['alert', 'Open'],
  RESOLVED: ['settled', 'Resolved'],
  ACTIVE: ['branch', 'Active'],
  CLOSED: ['settled', 'Closed'],
  PAID: ['settled', 'Paid'],
  PARTIALLY_PAID: ['agent', 'Part paid'],
}

export function StatusChip({ status, label, delayed }: { status: string; label?: string; delayed?: boolean }) {
  if (delayed) return <span className="chip alert">Delayed</span>
  const [tone, text] = STATUS[status] ?? ['neutral', status]
  return <span className={`chip ${tone}`}>{label ?? text}</span>
}

/* ------------------------------------------------------------------ layout bits */
export function PageHeader({ title, lede, actions }: { title: string; lede?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="page-head">
      <div>
        <h1>{title}</h1>
        {lede && <p className="lede">{lede}</p>}
      </div>
      {actions && <div className="actions">{actions}</div>}
    </header>
  )
}

export function Panel({ title, sub, actions, children, flush }: {
  title?: ReactNode; sub?: ReactNode; actions?: ReactNode; children: ReactNode; flush?: boolean
}) {
  return (
    <section className="panel">
      {title && (
        <div className="panel-head">
          <div>
            <h2>{title}</h2>
            {sub && <p>{sub}</p>}
          </div>
          {actions && <div className="spacer" />}
          {actions}
        </div>
      )}
      {flush ? children : <div className="panel-body">{children}</div>}
    </section>
  )
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      {children}
    </div>
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return <div className="loading" role="status">{label}</div>
}

export function ErrorNotice({ error }: { error: unknown }) {
  if (!error) return null
  const message = error instanceof Error ? error.message : 'Something went wrong.'
  return <div className="notice error" role="alert">{message}</div>
}

export function Pager({ page, count, pageSize = 25, onPage }: { page: number; count: number; pageSize?: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(count / pageSize))
  if (count <= pageSize) return <div className="pager"><span>{count} record{count === 1 ? '' : 's'}</span></div>
  return (
    <div className="pager">
      <span>{count} records · page {page} of {pages}</span>
      <div className="row">
        <button className="btn small" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</button>
        <button className="btn small" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</button>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ form field */
export function Field({ label, hint, error, children, className = '' }: {
  label: string; hint?: ReactNode; error?: string; children: (id: string) => ReactNode; className?: string
}) {
  const id = useId()
  return (
    <div className={`field ${className}`}>
      <label htmlFor={id}>{label}</label>
      {children(id)}
      {error ? <span className="error" id={`${id}-err`}>{error}</span> : hint ? <span className="hint">{hint}</span> : null}
    </div>
  )
}

/* ------------------------------------------------------------------ modal */
export function Modal({ title, lede, onClose, children, footer, wide }: {
  title: string; lede?: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean
}) {
  const ref = useRef<HTMLDivElement>(null)
  const titleId = useId()
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null
    const first = ref.current?.querySelector<HTMLElement>('input, select, textarea, button:not(.btn.ghost)')
    first?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      prev?.focus()
    }
  }, [onClose])
  return (
    <div className="backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`dialog ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-labelledby={titleId} ref={ref}>
        <div className="dialog-head">
          <h2 id={titleId}>{title}</h2>
          {lede && <p>{lede}</p>}
        </div>
        <div className="dialog-body">{children}</div>
        {footer && <div className="dialog-foot">{footer}</div>}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ toasts */
interface Toast { id: number; text: string; tone: 'ok' | 'error' }
const ToastCtx = createContext<(text: string, tone?: 'ok' | 'error') => void>(() => {})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const push = useCallback((text: string, tone: 'ok' | 'error' = 'ok') => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, text, tone }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">
        {toasts.map((t) => <div key={t.id} className={`toast ${t.tone === 'error' ? 'error' : ''}`}>{t.text}</div>)}
      </div>
    </ToastCtx.Provider>
  )
}

export const useToast = () => useContext(ToastCtx)

/** Message + per-field errors from an ApiError, for forms. */
export function useFormError() {
  const [error, setError] = useState<ApiError | null>(null)
  const fields = error?.fieldErrors ?? {}
  return {
    error,
    setError: (e: unknown) => setError(e instanceof ApiError ? e : e ? new ApiError(0, 'ERROR', String(e)) : null),
    field: (name: string) => fields[name],
    banner: error && (Object.keys(fields).length === 0 || fields.non_field_errors)
      ? <div className="notice error" role="alert">{fields.non_field_errors ?? error.message}</div>
      : null,
  }
}

/* ------------------------------------------------------------------ tabs */
export function Tabs<T extends string>({ value, onChange, items }: {
  value: T; onChange: (v: T) => void; items: { value: T; label: ReactNode }[]
}) {
  return (
    <div className="tabs" role="tablist">
      {items.map((it) => (
        <button key={it.value} role="tab" aria-selected={value === it.value} onClick={() => onChange(it.value)}>
          {it.label}
        </button>
      ))}
    </div>
  )
}
