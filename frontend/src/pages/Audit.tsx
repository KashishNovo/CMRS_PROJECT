import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { get } from '../api/client'
import type { AuditEntry, Paginated } from '../api/types'
import FilterBar from '../components/FilterBar'
import { Empty, ErrorNotice, Field, Loading, PageHeader, Pager, Panel } from '../components/ui'
import { fmtDateTime } from '../lib/format'
import { useFilters } from '../lib/hooks'

const ENTITIES = ['Collection', 'CashSubmission', 'BankDeposit', 'Discrepancy', 'Loan', 'Customer', 'User']

function describe(changes: Record<string, unknown>) {
  return Object.entries(changes)
    .filter(([, v]) => v !== null && v !== '' && !(Array.isArray(v) && v.length === 0))
    .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${Array.isArray(v) ? v.join(', ') : typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
    .join(' · ')
}

export default function Audit() {
  const f = useFilters({ date_from: '', date_to: '', branch: '', agent: '', status: '', entity_type: '', search: '' })
  const list = useQuery({
    queryKey: ['audit', f.params],
    queryFn: () => get<Paginated<AuditEntry>>('/audit-logs/', { ...f.params, agent: '', status: '' }),
    placeholderData: keepPreviousData,
  })
  return (
    <div className="stack">
      <PageHeader title="Audit trail" lede="Every change to a financial record: who did it, when, from where and what changed. Entries can’t be edited or deleted." />
      <FilterBar filters={f.filters} set={f.set} showAgent={false}>
        <Field label="Record type">
          {(id) => (
            <select id={id} className="select" value={f.filters.entity_type} onChange={(e) => f.set({ entity_type: e.target.value })}>
              <option value="">All records</option>
              {ENTITIES.map((e) => <option key={e} value={e}>{e}</option>)}
            </select>
          )}
        </Field>
        <Field label="Document number" className="wide">
          {(id) => <input id={id} type="search" className="input" value={f.filters.search} onChange={(e) => f.set({ search: e.target.value })} placeholder="e.g. RCP-MUM01-…" />}
        </Field>
      </FilterBar>
      <ErrorNotice error={list.error} />
      <Panel flush>
        {list.isLoading ? <Loading /> : !list.data?.results.length ? <Empty title="No entries" /> : (
          <>
            <div className="table-wrap">
              <table className="data">
                <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Record</th><th>Details</th></tr></thead>
                <tbody>
                  {list.data.results.map((e) => (
                    <tr key={e.id}>
                      <td className="nowrap">{fmtDateTime(e.created_at)}<span className="sub">{e.ip_address ?? ''}</span></td>
                      <td>{e.actor_name}<span className="sub">{e.branch_code ?? ''}</span></td>
                      <td className="nowrap">{e.action}</td>
                      <td className="nowrap">{e.entity_ref || `${e.entity_type} #${e.entity_id}`}</td>
                      <td className="small" style={{ maxWidth: 480 }}>{describe(e.changes)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager page={f.page} count={list.data.count} onPage={f.setPage} />
          </>
        )}
      </Panel>
    </div>
  )
}
