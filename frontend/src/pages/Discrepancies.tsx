import { useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { get, post } from '../api/client'
import type { Discrepancy, Paginated } from '../api/types'
import { useUser } from '../auth/AuthContext'
import FilterBar from '../components/FilterBar'
import { Amount, Empty, ErrorNotice, Field, Loading, Modal, PageHeader, Pager, Panel, StatusChip, useToast } from '../components/ui'
import { fmtDateTime } from '../lib/format'
import { useFilters } from '../lib/hooks'
import { inr } from '../lib/money'

const STAGE: Record<string, string> = {
  SUBMISSION: 'Agent → branch',
  DEPOSIT: 'Branch → bank',
  SETTLEMENT: 'Bank → company account',
}
const RESOLUTIONS = [
  { value: 'RECOVERED', label: 'Recovered from the responsible person' },
  { value: 'REFUNDED', label: 'Excess refunded or adjusted' },
  { value: 'BANK_CORRECTED', label: 'Corrected by the bank' },
  { value: 'WRITTEN_OFF', label: 'Written off' },
  { value: 'OTHER', label: 'Other' },
]

export default function Discrepancies() {
  const user = useUser()
  const [search] = useSearchParams()
  const f = useFilters({ date_from: '', date_to: '', branch: '', agent: '', status: search.get('status') ?? 'OPEN', stage: '' })
  const [open, setOpen] = useState<Discrepancy | null>(null)
  const list = useQuery({
    queryKey: ['discrepancies', f.params],
    queryFn: () => get<Paginated<Discrepancy>>('/discrepancies/', f.params),
    placeholderData: keepPreviousData,
  })

  return (
    <div className="stack">
      <PageHeader title="Discrepancies"
        lede="Raised automatically whenever a count, a deposit slip or a bank credit doesn’t match the figure before it. Each stays open until someone records how it was settled." />
      <FilterBar filters={f.filters} set={f.set} statuses={[{ value: 'OPEN', label: 'Open' }, { value: 'RESOLVED', label: 'Resolved' }]}>
        <Field label="Where it happened">
          {(id) => (
            <select id={id} className="select" value={f.filters.stage} onChange={(e) => f.set({ stage: e.target.value })}>
              <option value="">Any stage</option>
              {Object.entries(STAGE).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          )}
        </Field>
      </FilterBar>
      <ErrorNotice error={list.error} />
      <Panel flush>
        {list.isLoading ? <Loading /> : !list.data?.results.length ? (
          <Empty title={f.filters.status === 'OPEN' ? 'No open discrepancies' : 'Nothing matches these filters'}>
            {f.filters.status === 'OPEN' && 'Every count, deposit and credit in scope matches.'}
          </Empty>
        ) : (
          <>
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr><th>Raised</th><th>Where</th><th>Source</th><th className="right">Expected</th><th className="right">Actual</th><th className="right">Difference</th><th>Status</th></tr>
                </thead>
                <tbody>
                  {list.data.results.map((d) => (
                    <tr key={d.id} className="clickable" onClick={() => setOpen(d)}>
                      <td className="nowrap">{fmtDateTime(d.created_at)}<span className="sub">{d.branch_code}</span></td>
                      <td>{STAGE[d.stage]}{d.agent_name && <span className="sub">{d.agent_name}</span>}</td>
                      <td className="nowrap">{d.submission_number ?? d.deposit_number}</td>
                      <td className="right"><Amount value={d.expected_amount} /></td>
                      <td className="right"><Amount value={d.actual_amount} /></td>
                      <td className="right"><span className={`chip ${d.direction === 'SHORTAGE' ? 'alert' : 'count'}`}>{d.direction === 'SHORTAGE' ? 'Short' : 'Excess'} <Amount value={d.amount} /></span></td>
                      <td><StatusChip status={d.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager page={f.page} count={list.data.count} onPage={f.setPage} />
          </>
        )}
      </Panel>
      {open && <ResolveModal d={open} canResolve={open.status === 'OPEN' && user.role !== 'AGENT' && !(user.role === 'BRANCH_MANAGER' && open.stage === 'SETTLEMENT')} onClose={() => setOpen(null)} />}
    </div>
  )
}

function ResolveModal({ d, canResolve, onClose }: { d: Discrepancy; canResolve: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [resolution, setResolution] = useState(d.direction === 'EXCESS' ? 'REFUNDED' : d.stage === 'SETTLEMENT' ? 'BANK_CORRECTED' : 'RECOVERED')
  const [notes, setNotes] = useState('')
  const resolve = useMutation({
    mutationFn: () => post<Discrepancy>(`/discrepancies/${d.id}/resolve/`, { resolution, notes }),
    onSuccess: () => { toast('Discrepancy resolved'); qc.invalidateQueries(); onClose() },
  })
  return (
    <Modal title={`${d.direction === 'SHORTAGE' ? 'Shortage' : 'Excess'} of ${inr(d.amount)}`} onClose={onClose}
      lede={`${STAGE[d.stage]} · ${d.branch_code} · ${d.submission_number ?? d.deposit_number} · raised by ${d.raised_by_name} ${fmtDateTime(d.created_at)}`}
      footer={canResolve ? <>
        <button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn primary" disabled={!notes.trim() || resolve.isPending} onClick={() => resolve.mutate()}>Mark resolved</button>
      </> : <button className="btn primary" onClick={onClose}>Close</button>}>
      <div className="compare">
        <div><div className="k">Expected</div><div className="v"><Amount value={d.expected_amount} /></div></div>
        <div><div className="k">Actual</div><div className="v"><Amount value={d.actual_amount} /></div></div>
        <div className={d.direction === 'SHORTAGE' ? 'diff-short' : 'diff-excess'}><div className="k">{d.direction === 'SHORTAGE' ? 'Short' : 'Excess'}</div><div className="v"><Amount value={d.amount} /></div></div>
      </div>
      {d.reason && <div className="notice info">Recorded reason: {d.reason}</div>}
      {d.status === 'RESOLVED' && (
        <div className="notice ok">Resolved by {d.resolved_by_name} {fmtDateTime(d.resolved_at)}: {RESOLUTIONS.find((r) => r.value === d.resolution)?.label}. {d.resolution_notes}</div>
      )}
      {canResolve && (
        <>
          <ErrorNotice error={resolve.error} />
          <Field label="How was it settled?">
            {(id) => (
              <select id={id} className="select" value={resolution} onChange={(e) => setResolution(e.target.value)}>
                {RESOLUTIONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            )}
          </Field>
          <Field label="Details" hint="Reference any recovery receipt, bank letter or approval.">
            {(id) => <textarea id={id} className="textarea" value={notes} onChange={(e) => setNotes(e.target.value)} />}
          </Field>
        </>
      )}
    </Modal>
  )
}
