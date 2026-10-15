import { useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { get, post } from '../api/client'
import type { Collection, Paginated } from '../api/types'
import { useUser } from '../auth/AuthContext'
import { ReceiptSlip } from '../components/AgentModals'
import FilterBar from '../components/FilterBar'
import { Amount, Empty, ErrorNotice, Field, Loading, Modal, PageHeader, Pager, Panel, StatusChip, useToast } from '../components/ui'
import { fmtDateTime } from '../lib/format'
import { useFilters } from '../lib/hooks'

const STATUSES = [
  { value: 'COLLECTED', label: 'With agent' },
  { value: 'SUBMITTED', label: 'Awaiting count' },
  { value: 'BRANCH_RECEIVED', label: 'In branch' },
  { value: 'DEPOSITED', label: 'Deposited' },
  { value: 'SETTLED', label: 'Settled' },
  { value: 'VOIDED', label: 'Voided' },
]

export default function Collections() {
  const user = useUser()
  const [search] = useSearchParams()
  const f = useFilters({ date_from: '', date_to: '', branch: '', agent: '', status: search.get('status') ?? '', search: '' })
  const [open, setOpen] = useState<Collection | null>(null)
  const list = useQuery({
    queryKey: ['collections', f.params],
    queryFn: () => get<Paginated<Collection>>('/collections/', f.params),
    placeholderData: keepPreviousData,
  })

  return (
    <div className="stack">
      <PageHeader title="Receipts" lede={user.role === 'AGENT'
        ? 'Every repayment you have recorded and where its cash is now.'
        : 'Every repayment recorded by agents, and where its cash is now.'} />
      <FilterBar filters={f.filters} set={f.set} statuses={STATUSES}>
        <Field label="Receipt, customer or loan" className="wide">
          {(id) => <input id={id} type="search" className="input" value={f.filters.search} onChange={(e) => f.set({ search: e.target.value })} />}
        </Field>
      </FilterBar>
      <ErrorNotice error={list.error} />
      <Panel flush>
        {list.isLoading ? <Loading /> : !list.data?.results.length ? <Empty title="No receipts match these filters" /> : (
          <>
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr><th>Receipt</th><th>Collected</th><th>Customer</th>{user.role !== 'AGENT' && <th>Agent</th>}<th className="right">Amount</th><th>Where the cash is</th></tr>
                </thead>
                <tbody>
                  {list.data.results.map((c) => (
                    <tr key={c.id} className="clickable" onClick={() => setOpen(c)}>
                      <td className="nowrap">{c.receipt_number}</td>
                      <td className="nowrap">{fmtDateTime(c.collected_at)}</td>
                      <td>{c.customer_name}<span className="sub">{c.loan_number}</span></td>
                      {user.role !== 'AGENT' && <td>{c.agent_name}<span className="sub">{c.branch_code}</span></td>}
                      <td className="right"><Amount value={c.amount} /></td>
                      <td><StatusChip status={c.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager page={f.page} count={list.data.count} onPage={f.setPage} />
          </>
        )}
      </Panel>
      {open && <ReceiptModal c={open} onClose={() => setOpen(null)} />}
    </div>
  )
}

function ReceiptModal({ c, onClose }: { c: Collection; onClose: () => void }) {
  const user = useUser()
  const qc = useQueryClient()
  const toast = useToast()
  const [voiding, setVoiding] = useState(false)
  const [reason, setReason] = useState('')
  const canVoid = c.status === 'COLLECTED' && (user.role === 'BRANCH_MANAGER' || user.role === 'ADMIN' || (user.role === 'AGENT' && user.id === c.agent))
  const voidIt = useMutation({
    mutationFn: () => post<Collection>(`/collections/${c.id}/void/`, { reason }),
    onSuccess: (r) => {
      toast(`Receipt ${r.receipt_number} voided; the loan balance is restored`)
      qc.invalidateQueries()
      onClose()
    },
  })
  return (
    <Modal title={voiding ? `Void receipt ${c.receipt_number}?` : 'Receipt'} onClose={onClose}
      lede={voiding ? 'Use this only for a receipt entered in error. The payment is reversed from the loan and the receipt stays on record as voided.' : undefined}
      footer={voiding ? <>
        <button className="btn ghost" onClick={() => setVoiding(false)}>Keep receipt</button>
        <button className="btn solid-danger" disabled={!reason.trim() || voidIt.isPending} onClick={() => voidIt.mutate()}>Void receipt</button>
      </> : <>
        {canVoid && <button className="btn danger" onClick={() => setVoiding(true)}>Void receipt</button>}
        <span className="spacer" />
        <button className="btn primary" onClick={onClose}>Close</button>
      </>}>
      {voiding ? (
        <>
          <ErrorNotice error={voidIt.error} />
          <Field label="Reason">
            {(id) => <input id={id} className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. recorded against the wrong customer" />}
          </Field>
        </>
      ) : (
        <>
          <ReceiptSlip c={c} />
          {c.status !== 'COLLECTED' && c.status !== 'VOIDED' && (
            <p className="small muted">This receipt has left the agent’s custody, so it is locked. Corrections are made through the discrepancy process.</p>
          )}
        </>
      )}
    </Modal>
  )
}
