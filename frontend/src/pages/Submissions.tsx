import { useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { get, post } from '../api/client'
import type { Paginated, Submission } from '../api/types'
import { useUser } from '../auth/AuthContext'
import { HandoverModal } from '../components/AgentModals'
import FilterBar from '../components/FilterBar'
import { Amount, Empty, ErrorNotice, Field, Loading, Modal, PageHeader, Pager, Panel, StatusChip, useToast } from '../components/ui'
import { fmtDateTime, fmtTime } from '../lib/format'
import { useFilters } from '../lib/hooks'
import { compare, inr, isValidAmount, subtract } from '../lib/money'

const STATUSES = [
  { value: 'PENDING', label: 'Awaiting count' },
  { value: 'APPROVED', label: 'Approved' },
  { value: 'REJECTED', label: 'Rejected' },
]

export default function Submissions() {
  const user = useUser()
  const [search] = useSearchParams()
  const reviewer = user.role === 'BRANCH_MANAGER' || user.role === 'ADMIN'
  const f = useFilters({ date_from: '', date_to: '', branch: '', agent: '', status: search.get('status') ?? (reviewer ? 'PENDING' : '') })
  const [openId, setOpenId] = useState<number | null>(null)
  const [handover, setHandover] = useState(false)
  const list = useQuery({
    queryKey: ['submissions', f.params],
    queryFn: () => get<Paginated<Submission>>('/submissions/', f.params),
    placeholderData: keepPreviousData,
  })

  return (
    <div className="stack">
      <PageHeader
        title={user.role === 'AGENT' ? 'My hand-overs' : 'Cash hand-overs'}
        lede={user.role === 'AGENT'
          ? 'Cash you have handed to the branch, and what the manager counted.'
          : 'Agents hand over the cash for a batch of receipts. Count it, then approve or reject the hand-over.'}
        actions={user.role === 'AGENT' && <button className="btn primary" onClick={() => setHandover(true)}>Hand over cash</button>}
      />
      <FilterBar filters={f.filters} set={f.set} statuses={STATUSES} />
      <ErrorNotice error={list.error} />
      <Panel flush>
        {list.isLoading ? <Loading /> : !list.data?.results.length ? (
          <Empty title={f.filters.status === 'PENDING' ? 'No cash waiting to be counted' : 'No hand-overs match these filters'} />
        ) : (
          <>
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Hand-over</th><th>Agent</th><th className="right">Receipts total</th><th className="right">Declared</th>
                    <th className="right">Counted</th><th className="right">Difference</th><th>Status</th><th />
                  </tr>
                </thead>
                <tbody>
                  {list.data.results.map((s) => (
                    <tr key={s.id} className="clickable" onClick={() => setOpenId(s.id)}>
                      <td className="nowrap">{s.submission_number}<span className="sub">{fmtDateTime(s.created_at)} · {s.receipt_count} receipts</span></td>
                      <td>{s.agent_name}<span className="sub">{s.branch_code}</span></td>
                      <td className="right"><Amount value={s.expected_amount} /></td>
                      <td className="right"><Amount value={s.declared_amount} /></td>
                      <td className="right"><Amount value={s.received_amount} /></td>
                      <td className="right"><Difference value={s.difference} /></td>
                      <td><StatusChip status={s.status} /></td>
                      <td className="right">{reviewer && s.status === 'PENDING' && <button className="btn small primary">Count</button>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager page={f.page} count={list.data.count} onPage={f.setPage} />
          </>
        )}
      </Panel>
      {openId && <SubmissionModal id={openId} onClose={() => setOpenId(null)} />}
      {handover && <HandoverModal onClose={() => setHandover(false)} />}
    </div>
  )
}

/** Shortage (expected > received) is shown as a negative, excess as a positive. */
export function Difference({ value }: { value: string | null }) {
  if (value === null) return <span className="muted">—</span>
  const c = compare(value, '0')
  if (c === 0) return <span className="muted">None</span>
  return <span className="amount" style={{ color: c > 0 ? 'var(--alert)' : 'var(--stage-count)' }}>{c > 0 ? 'Short ' : 'Over '}{inr(value.replace('-', ''))}</span>
}

function SubmissionModal({ id, onClose }: { id: number; onClose: () => void }) {
  const user = useUser()
  const qc = useQueryClient()
  const toast = useToast()
  const detail = useQuery({ queryKey: ['submission', id], queryFn: () => get<Submission>(`/submissions/${id}/`) })
  const [counted, setCounted] = useState('')
  const [notes, setNotes] = useState('')
  const [rejecting, setRejecting] = useState(false)
  const s = detail.data
  const canReview = s?.status === 'PENDING' && (user.role === 'BRANCH_MANAGER' || user.role === 'ADMIN')
  const diff = s && isValidAmount(counted) ? subtract(s.expected_amount, counted) : null
  const diffSign = diff ? compare(diff, '0') : 0

  const done = (msg: string) => {
    toast(msg)
    qc.invalidateQueries()
    onClose()
  }
  const approve = useMutation({
    mutationFn: () => post<Submission>(`/submissions/${id}/approve/`, { received_amount: counted, notes }),
    onSuccess: (r) => done(compare(r.difference ?? '0', '0') === 0
      ? `${r.submission_number} approved: cash matches`
      : `${r.submission_number} approved with a discrepancy of ${inr((r.difference ?? '0').replace('-', ''))}`),
  })
  const reject = useMutation({
    mutationFn: () => post<Submission>(`/submissions/${id}/reject/`, { reason: notes }),
    onSuccess: (r) => done(`${r.submission_number} rejected; the cash stays with the agent`),
  })
  const error = approve.error ?? reject.error

  return (
    <Modal wide title={s ? `Hand-over ${s.submission_number}` : 'Hand-over'}
      lede={s && `${s.agent_name} · ${s.branch_code} · handed over ${fmtDateTime(s.created_at)}`}
      onClose={onClose}
      footer={!canReview ? <button className="btn primary" onClick={onClose}>Close</button> : rejecting ? <>
        <button className="btn ghost" onClick={() => setRejecting(false)}>Back</button>
        <button className="btn solid-danger" disabled={!notes.trim() || reject.isPending} onClick={() => reject.mutate()}>Reject hand-over</button>
      </> : <>
        <button className="btn danger" onClick={() => setRejecting(true)}>Reject…</button>
        <span className="spacer" />
        <button className="btn primary" disabled={!isValidAmount(counted) || approve.isPending || (diffSign !== 0 && !notes.trim())}
          onClick={() => approve.mutate()}>
          {diffSign === 0 ? 'Approve' : 'Approve with discrepancy'}
        </button>
      </>}>
      {!s ? <Loading /> : (
        <>
          <ErrorNotice error={error} />
          {s.agent_notes && <div className="notice info">Agent’s note: {s.agent_notes}</div>}
          {canReview && !rejecting && (
            <>
              <div className="form-grid">
                <Field label="Cash you counted (₹)" hint="Count the notes before entering the figure; don’t copy the expected amount.">
                  {(fid) => <input id={fid} className="input money" inputMode="decimal" value={counted} autoFocus
                    onChange={(e) => setCounted(e.target.value.replace(/[^\d.]/g, ''))} />}
                </Field>
                <Field label={diffSign === 0 ? 'Notes (optional)' : 'Explain the difference'}>
                  {(fid) => <input id={fid} className="input" value={notes} onChange={(e) => setNotes(e.target.value)} aria-invalid={diffSign !== 0 && !notes.trim()} />}
                </Field>
              </div>
              <div className="compare">
                <div><div className="k">Expected (receipts)</div><div className="v"><Amount value={s.expected_amount} /></div></div>
                <div><div className="k">Received (counted)</div><div className="v">{isValidAmount(counted) ? <Amount value={counted} /> : '—'}</div></div>
                <div className={diff === null ? '' : diffSign === 0 ? 'diff-ok' : diffSign > 0 ? 'diff-short' : 'diff-excess'}>
                  <div className="k">{diffSign > 0 ? 'Shortage' : diffSign < 0 ? 'Excess' : 'Difference'}</div>
                  <div className="v">{diff === null ? '—' : <Amount value={diff.replace('-', '')} />}</div>
                </div>
              </div>
              {compare(s.declared_amount, s.expected_amount) !== 0 && (
                <div className="notice warn">The agent declared <b>{inr(s.declared_amount)}</b>, not the receipts total.</div>
              )}
            </>
          )}
          {canReview && rejecting && (
            <Field label="Why are you rejecting this cash?" hint="The receipts go back to the agent’s custody; they can hand them over again.">
              {(fid) => <input id={fid} className="input" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. suspected counterfeit ₹500 notes" />}
            </Field>
          )}
          {!canReview && (
            <div className="compare">
              <div><div className="k">Expected (receipts)</div><div className="v"><Amount value={s.expected_amount} /></div></div>
              <div><div className="k">Received (counted)</div><div className="v"><Amount value={s.received_amount} /></div></div>
              <div className={s.difference === null ? '' : compare(s.difference, '0') === 0 ? 'diff-ok' : compare(s.difference, '0') > 0 ? 'diff-short' : 'diff-excess'}>
                <div className="k">Difference</div><div className="v"><Difference value={s.difference} /></div>
              </div>
            </div>
          )}
          {s.status !== 'PENDING' && (
            <p className="small"><StatusChip status={s.status} /> by {s.reviewed_by_name} on {fmtDateTime(s.reviewed_at)}{s.review_notes && `: ${s.review_notes}`}
              {s.deposit_numbers.length > 0 && <> · banked in {s.deposit_numbers.join(', ')}</>}</p>
          )}
          <div className="table-wrap panel">
            <table className="data">
              <thead><tr><th>Receipt</th><th>Customer</th><th>Time</th><th className="right">Amount</th><th>Status</th></tr></thead>
              <tbody>
                {s.collections?.map((c) => (
                  <tr key={c.id}>
                    <td className="nowrap">{c.receipt_number}</td><td>{c.customer_name}</td><td className="nowrap">{fmtTime(c.collected_at)}</td>
                    <td className="right"><Amount value={c.amount} /></td><td><StatusChip status={c.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Modal>
  )
}
