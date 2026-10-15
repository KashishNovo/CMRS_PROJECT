import { useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { get, post } from '../api/client'
import type { Deposit, Paginated, Submission } from '../api/types'
import { useUser } from '../auth/AuthContext'
import FilterBar from '../components/FilterBar'
import { Amount, Empty, ErrorNotice, Field, Loading, Modal, PageHeader, Pager, Panel, StatusChip, useFormError, useToast } from '../components/ui'
import { fmtDate, fmtDateTime, isoDate } from '../lib/format'
import { useFilters } from '../lib/hooks'
import { compare, inr, isValidAmount, subtract, sum } from '../lib/money'
import { Difference } from './Submissions'

const STATUSES = [
  { value: 'PENDING_SETTLEMENT', label: 'Awaiting credit' },
  { value: 'SETTLED', label: 'Settled' },
  { value: 'SETTLEMENT_MISMATCH', label: 'Credit mismatch' },
  { value: 'FAILED', label: 'Failed' },
]

export default function Deposits() {
  const user = useUser()
  const [search] = useSearchParams()
  const f = useFilters({ date_from: '', date_to: '', branch: '', agent: '', status: search.get('status') ?? (user.role === 'FINANCE' ? 'PENDING_SETTLEMENT' : ''), delayed: '' })
  const [openId, setOpenId] = useState<number | null>(null)
  const list = useQuery({
    queryKey: ['deposits', f.params],
    queryFn: () => get<Paginated<Deposit>>('/deposits/', f.params),
    placeholderData: keepPreviousData,
  })

  return (
    <div className="stack">
      <PageHeader
        title={user.role === 'FINANCE' ? 'Settlements' : 'Bank deposits'}
        lede={user.role === 'FINANCE'
          ? 'Match each branch deposit against the credit on the company bank statement.'
          : 'Bank the cash verified at your branch and follow it until the bank credits it.'}
      />
      {user.role === 'BRANCH_MANAGER' && <CashInSafe />}
      <FilterBar filters={f.filters} set={f.set} statuses={STATUSES} dateLabel="Deposited from" showAgent={false}>
        <label className="check" style={{ alignSelf: 'center', marginTop: 18 }}>
          <input type="checkbox" checked={f.filters.delayed === 'true'} onChange={(e) => f.set({ delayed: e.target.checked ? 'true' : '' })} />
          Only past settlement SLA
        </label>
      </FilterBar>
      <ErrorNotice error={list.error} />
      <Panel flush>
        {list.isLoading ? <Loading /> : !list.data?.results.length ? <Empty title="No deposits match these filters" /> : (
          <>
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Deposit</th><th>Bank & reference</th><th className="right">Verified cash</th><th className="right">Deposited</th>
                    <th className="right">Credited</th><th>Status</th><th />
                  </tr>
                </thead>
                <tbody>
                  {list.data.results.map((d) => (
                    <tr key={d.id} className="clickable" onClick={() => setOpenId(d.id)}>
                      <td className="nowrap">{d.deposit_number}<span className="sub">{d.branch_code} · {fmtDate(d.deposit_date)}</span></td>
                      <td>{d.bank_name}<span className="sub">{d.reference_number}</span></td>
                      <td className="right"><Amount value={d.reconciled_amount} /></td>
                      <td className="right"><Amount value={d.amount} />{compare(d.deposit_difference, '0') !== 0 && <span className="sub"><Difference value={d.deposit_difference} /></span>}</td>
                      <td className="right"><Amount value={d.settled_amount} />{d.settlement_difference && compare(d.settlement_difference, '0') !== 0 && <span className="sub"><Difference value={d.settlement_difference} /></span>}</td>
                      <td><StatusChip status={d.status} delayed={d.is_delayed} /></td>
                      <td className="right">{(user.role === 'FINANCE' || user.role === 'ADMIN') && d.status === 'PENDING_SETTLEMENT' && <button className="btn small primary">Match credit</button>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager page={f.page} count={list.data.count} onPage={f.setPage} />
          </>
        )}
      </Panel>
      {openId && <DepositModal id={openId} onClose={() => setOpenId(null)} />}
    </div>
  )
}

/* ------------------------------------------------------------------ manager: approved cash waiting to be banked */
function CashInSafe() {
  const available = useQuery({ queryKey: ['available-submissions'], queryFn: () => get<Submission[]>('/deposits/available-submissions/') })
  const [creating, setCreating] = useState(false)
  const rows = available.data ?? []
  const total = sum(rows.map((r) => r.received_amount))
  return (
    <Panel title="Cash in the branch safe" sub="Approved hand-overs not yet banked."
      actions={rows.length > 0 && <button className="btn primary" onClick={() => setCreating(true)}>Record bank deposit</button>} flush>
      {available.isLoading ? <Loading /> : rows.length === 0 ? <Empty title="The safe is clear">All verified cash has been banked.</Empty> : (
        <div className="panel-body row">
          <div><div className="muted small">{rows.length} hand-over{rows.length > 1 ? 's' : ''}</div><div style={{ fontSize: '1.6rem', fontWeight: 700, fontStretch: '80%' }}><Amount value={total} /></div></div>
          <div className="spacer" />
          <p className="muted small" style={{ maxWidth: '52ch' }}>Deposit at the bank first, then record the slip’s reference number here so Finance can match the credit.</p>
        </div>
      )}
      {creating && <NewDepositModal subs={rows} onClose={() => setCreating(false)} />}
    </Panel>
  )
}

function NewDepositModal({ subs, onClose }: { subs: Submission[]; onClose: () => void }) {
  const user = useUser()
  const qc = useQueryClient()
  const toast = useToast()
  const err = useFormError()
  const [chosen, setChosen] = useState<Set<number>>(new Set(subs.map((s) => s.id)))
  const reconciled = sum(subs.filter((s) => chosen.has(s.id)).map((s) => s.received_amount))
  const [form, setForm] = useState({ bank_name: '', account_number: '', reference_number: '', deposit_date: isoDate(), amount: '', mismatch_reason: '' })
  const set = (p: Partial<typeof form>) => setForm((f) => ({ ...f, ...p }))
  const amount = form.amount === '' ? reconciled : form.amount
  const diff = isValidAmount(amount) ? subtract(reconciled, amount) : '0'
  const mismatch = compare(diff, '0') !== 0

  const save = useMutation({
    mutationFn: () => post<Deposit>('/deposits/', { ...form, amount, submission_ids: [...chosen] }),
    onSuccess: (d) => {
      toast(`Deposit ${d.deposit_number} recorded; awaiting bank credit`)
      qc.invalidateQueries()
      onClose()
    },
    onError: err.setError,
  })
  const toggle = (id: number) => setChosen((c) => {
    const n = new Set(c)
    if (n.has(id)) n.delete(id)
    else n.add(id)
    return n
  })

  return (
    <Modal wide title="Record bank deposit" lede={`Cash from ${user.branch_detail?.name} deposited into the company account.`} onClose={onClose}
      footer={<>
        <button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn primary" disabled={save.isPending || !chosen.size || !form.bank_name || !form.reference_number || !isValidAmount(amount) || (mismatch && !form.mismatch_reason.trim())}
          onClick={() => save.mutate()}>Record deposit of {isValidAmount(amount) ? inr(amount) : '…'}</button>
      </>}>
      {err.banner}
      <div className="table-wrap panel">
        <table className="data">
          <thead><tr><th><span className="sr-only">Include</span></th><th>Hand-over</th><th>Agent</th><th>Approved</th><th className="right">Verified cash</th></tr></thead>
          <tbody>
            {subs.map((s) => (
              <tr key={s.id} className={chosen.has(s.id) ? 'selected clickable' : 'clickable'} onClick={() => toggle(s.id)}>
                <td><input type="checkbox" checked={chosen.has(s.id)} onChange={() => toggle(s.id)} onClick={(e) => e.stopPropagation()} aria-label={`Include ${s.submission_number}`} /></td>
                <td className="nowrap">{s.submission_number}</td><td>{s.agent_name}</td><td className="nowrap">{fmtDateTime(s.reviewed_at)}</td>
                <td className="right"><Amount value={s.received_amount} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="form-grid">
        <Field label="Bank" error={err.field('bank_name')}>
          {(id) => <input id={id} className="input" value={form.bank_name} onChange={(e) => set({ bank_name: e.target.value })} placeholder="e.g. HDFC Bank" />}
        </Field>
        <Field label="Company account number" error={err.field('account_number')}>
          {(id) => <input id={id} className="input" value={form.account_number} onChange={(e) => set({ account_number: e.target.value })} />}
        </Field>
        <Field label="Slip / transaction reference" error={err.field('reference_number')} hint="Must be unique: the same reference can’t be recorded twice.">
          {(id) => <input id={id} className="input" value={form.reference_number} onChange={(e) => set({ reference_number: e.target.value })} />}
        </Field>
        <Field label="Deposit date" error={err.field('deposit_date')}>
          {(id) => <input id={id} className="input" type="date" max={isoDate()} value={form.deposit_date} onChange={(e) => set({ deposit_date: e.target.value })} />}
        </Field>
        <Field label="Amount on the slip (₹)" error={err.field('amount')}>
          {(id) => <input id={id} className="input money" inputMode="decimal" value={amount} onChange={(e) => set({ amount: e.target.value.replace(/[^\d.]/g, '') })} />}
        </Field>
        <Field label="Verified cash selected">
          {(id) => <input id={id} className="input money" value={inr(reconciled)} readOnly />}
        </Field>
        {mismatch && (
          <Field label={`Why does the slip differ by ${inr(diff.replace('-', ''))}?`} className="full" hint="A deposit discrepancy will be raised for follow-up.">
            {(id) => <input id={id} className="input" value={form.mismatch_reason} onChange={(e) => set({ mismatch_reason: e.target.value })} aria-invalid={!form.mismatch_reason.trim()} />}
          </Field>
        )}
      </div>
    </Modal>
  )
}

/* ------------------------------------------------------------------ deposit detail + finance settlement */
function DepositModal({ id, onClose }: { id: number; onClose: () => void }) {
  const user = useUser()
  const qc = useQueryClient()
  const toast = useToast()
  const detail = useQuery({ queryKey: ['deposit', id], queryFn: () => get<Deposit>(`/deposits/${id}/`) })
  const d = detail.data
  const canSettle = d?.status === 'PENDING_SETTLEMENT' && (user.role === 'FINANCE' || user.role === 'ADMIN')
  const [mode, setMode] = useState<'settle' | 'fail'>('settle')
  const [form, setForm] = useState({ settled_amount: '', settlement_date: isoDate(), settlement_reference: '', notes: '' })
  const set = (p: Partial<typeof form>) => setForm((f) => ({ ...f, ...p }))
  const credited = form.settled_amount === '' ? d?.amount ?? '' : form.settled_amount
  const diff = d && isValidAmount(credited) ? subtract(d.amount, credited) : '0'
  const mismatch = compare(diff, '0') !== 0

  const finish = (msg: string) => { toast(msg); qc.invalidateQueries(); onClose() }
  const settle = useMutation({
    mutationFn: () => post<Deposit>(`/deposits/${id}/settle/`, { ...form, settled_amount: credited }),
    onSuccess: (r) => finish(r.status === 'SETTLED' ? `${r.deposit_number} settled` : `${r.deposit_number} settled with a mismatch; discrepancy raised`),
  })
  const fail = useMutation({
    mutationFn: () => post<Deposit>(`/deposits/${id}/fail/`, { reason: form.notes }),
    onSuccess: (r) => finish(`${r.deposit_number} marked failed; the cash is back in the branch safe`),
  })

  return (
    <Modal wide title={d ? `Deposit ${d.deposit_number}` : 'Deposit'} onClose={onClose}
      lede={d && `${d.branch_code} · ${d.bank_name} ${d.account_number} · ref ${d.reference_number} · deposited ${fmtDate(d.deposit_date)} by ${d.created_by_name}`}
      footer={!canSettle ? <button className="btn primary" onClick={onClose}>Close</button> : mode === 'settle' ? <>
        <button className="btn danger" onClick={() => setMode('fail')}>Not credited…</button>
        <span className="spacer" />
        <button className="btn primary" disabled={settle.isPending || !isValidAmount(credited) || (mismatch && !form.notes.trim())} onClick={() => settle.mutate()}>
          {mismatch ? 'Confirm credit with mismatch' : 'Confirm credit'}
        </button>
      </> : <>
        <button className="btn ghost" onClick={() => setMode('settle')}>Back</button>
        <button className="btn solid-danger" disabled={fail.isPending || !form.notes.trim()} onClick={() => fail.mutate()}>Mark deposit failed</button>
      </>}>
      {!d ? <Loading /> : (
        <>
          <ErrorNotice error={settle.error ?? fail.error} />
          <div className="compare">
            <div><div className="k">Verified at branch</div><div className="v"><Amount value={d.reconciled_amount} /></div></div>
            <div><div className="k">Deposited (slip)</div><div className="v"><Amount value={d.amount} /></div></div>
            <div className={d.settled_amount === null ? '' : compare(d.settlement_difference ?? '0', '0') === 0 ? 'diff-ok' : 'diff-short'}>
              <div className="k">Credited by bank</div><div className="v"><Amount value={d.settled_amount} /></div>
            </div>
          </div>
          {d.mismatch_reason && <div className="notice warn">Slip differs from verified cash: {d.mismatch_reason}</div>}
          {d.is_delayed && <div className="notice error">This deposit is past the settlement SLA. Chase the bank or mark it failed.</div>}
          {d.status === 'FAILED' && <div className="notice error">Failed: {d.failure_reason}</div>}
          {d.settled_at && d.status !== 'FAILED' && (
            <p className="small"><StatusChip status={d.status} /> {fmtDate(d.settlement_date)} {d.settlement_reference && `(${d.settlement_reference})`}, confirmed by {d.settled_by_name} {fmtDateTime(d.settled_at)}{d.settlement_notes && `: ${d.settlement_notes}`}</p>
          )}
          {canSettle && mode === 'settle' && (
            <div className="form-grid">
              <Field label="Amount credited on statement (₹)">
                {(fid) => <input id={fid} className="input money" inputMode="decimal" value={credited} onChange={(e) => set({ settled_amount: e.target.value.replace(/[^\d.]/g, '') })} />}
              </Field>
              <Field label="Credit date">
                {(fid) => <input id={fid} className="input" type="date" min={d.deposit_date} max={isoDate()} value={form.settlement_date} onChange={(e) => set({ settlement_date: e.target.value })} />}
              </Field>
              <Field label="Statement reference (optional)">
                {(fid) => <input id={fid} className="input" value={form.settlement_reference} onChange={(e) => set({ settlement_reference: e.target.value })} />}
              </Field>
              <Field label={mismatch ? `Explain the ${inr(diff.replace('-', ''))} difference` : 'Notes (optional)'}>
                {(fid) => <input id={fid} className="input" value={form.notes} onChange={(e) => set({ notes: e.target.value })} aria-invalid={mismatch && !form.notes.trim()} />}
              </Field>
            </div>
          )}
          {canSettle && mode === 'fail' && (
            <Field label="What happened?" hint="The receipts return to the branch safe so the cash can be deposited again with a new slip.">
              {(fid) => <input id={fid} className="input" value={form.notes} onChange={(e) => set({ notes: e.target.value })} placeholder="e.g. slip returned: account number mismatch" />}
            </Field>
          )}
          <div className="table-wrap panel">
            <table className="data">
              <thead><tr><th>Hand-over</th><th>Agent</th><th className="right">Receipts total</th><th className="right">Verified cash</th></tr></thead>
              <tbody>
                {d.submissions?.map((s) => (
                  <tr key={s.id}><td>{s.submission_number}</td><td>{s.agent_name}</td><td className="right"><Amount value={s.expected_amount} /></td><td className="right"><Amount value={s.received_amount} /></td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Modal>
  )
}
