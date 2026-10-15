import type { ReactNode } from 'react'
import { useUser } from '../auth/AuthContext'
import { useAgents, useBranches } from '../lib/hooks'
import { Field } from './ui'

export interface CommonFilters {
  date_from: string
  date_to: string
  branch: string
  agent: string
  status: string
  [key: string]: string
}

/**
 * Date range, branch, agent and status filters. Branch is shown only to roles that span
 * branches, agent only to roles that supervise agents; the API enforces the same scoping.
 */
export default function FilterBar({ filters, set, statuses, children, dateLabel = 'From', showAgent = true }: {
  filters: CommonFilters
  set: (patch: Partial<CommonFilters>) => void
  statuses?: { value: string; label: string }[]
  children?: ReactNode
  dateLabel?: string
  showAgent?: boolean
}) {
  const user = useUser()
  const global = user.role === 'ADMIN' || user.role === 'FINANCE'
  const branches = useBranches()
  const agents = useAgents(global ? filters.branch || null : user.branch, showAgent && user.role !== 'AGENT')

  return (
    <div className="filters" role="search">
      <Field label={dateLabel}>
        {(id) => <input id={id} type="date" className="input" value={filters.date_from} max={filters.date_to || undefined}
          onChange={(e) => set({ date_from: e.target.value })} />}
      </Field>
      <Field label="To">
        {(id) => <input id={id} type="date" className="input" value={filters.date_to} min={filters.date_from || undefined}
          onChange={(e) => set({ date_to: e.target.value })} />}
      </Field>
      {global && (
        <Field label="Branch">
          {(id) => (
            <select id={id} className="select" value={filters.branch} onChange={(e) => set({ branch: e.target.value, agent: '' })}>
              <option value="">All branches</option>
              {branches.data?.map((b) => <option key={b.id} value={b.id}>{b.code} · {b.city || b.name}</option>)}
            </select>
          )}
        </Field>
      )}
      {showAgent && user.role !== 'AGENT' && (
        <Field label="Agent">
          {(id) => (
            <select id={id} className="select" value={filters.agent} onChange={(e) => set({ agent: e.target.value })}>
              <option value="">All agents</option>
              {agents.data?.map((a) => <option key={a.id} value={a.id}>{a.full_name}</option>)}
            </select>
          )}
        </Field>
      )}
      {statuses && (
        <Field label="Status">
          {(id) => (
            <select id={id} className="select" value={filters.status} onChange={(e) => set({ status: e.target.value })}>
              <option value="">Any status</option>
              {statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          )}
        </Field>
      )}
      {children}
    </div>
  )
}
