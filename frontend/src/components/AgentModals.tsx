import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, get, post } from '../api/client'
import type { Collection, Loan, Paginated, Submission } from '../api/types'
import { fmtDate, fmtDateTime, fmtTime } from '../lib/format'
import { compare, inr, isValidAmount, subtract, sum, toPaise } from '../lib/money'
import { Amount, Empty, Field, Loading, Modal, StatusChip, useToast } from './ui'

function newKey() {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`.replace(/[^0-9a-f]/g, '').padEnd(32, '0').replace(/^(.{8})(.{4})(.{4})(.{4})(.{12}).*/, '$1-$2-$3-$4-$5')
}

/* ------------------------------------------------------------------ record a repayment */
export function RecordPaymentModal({ loan, onClose }: { loan: Loan; onClose: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  // One key per payment attempt: a double tap or network retry returns the same receipt.
  const [key] = useState(newKey)
  const [amount, setAmount] = useState(loan.next_due_amount ?? '')
  const [remarks, setRemarks] = useState('')
  const [duplicate, setDuplicate] = useState<ApiError | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [receipt, setReceipt] = useState<Collection | null>(null)

  const over = isValidAmount(amount) && compare(amount, loan.outstanding) > 0
  const partial = isValidAmount(amount) && loan.next_due_amount && compare(amount, loan.next_due_amount) < 0

  const save = useMutation({
    mutationFn: (confirm: boolean) =>
      post<Collection>('/collections/', { loan: loan.id, amount, remarks, idempotency_key: key, confirm_duplicate: confirm }),
    onSuccess: (c) => {
      setReceipt(c)
      toast(`Receipt ${c.receipt_number} recorded`)
      qc.invalidateQueries()
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === 'POSSIBLE_DUPLICATE') setDuplicate(e)
      else setError(e as ApiError)
    },
  })

  if (receipt) {
    return (
      <Modal title="Payment recorded" onClose={onClose} footer={<>
        <button className="btn" onClick={() => window.print()}>Print receipt</button>
        <button className="btn primary" onClick={onClose}>Done</button>
      </>}>
        <ReceiptSlip c={receipt} />
      </Modal>
    )
  }

  return (
    <Modal
      title={`Record payment from ${loan.customer_name}`}
      lede={`Loan ${loan.loan_number}. Outstanding ${inr(loan.outstanding)}${loan.next_due_date ? `, next instalment ${inr(loan.next_due_amount)} due ${fmtDate(loan.next_due_date)}` : ''}.`}
      onClose={onClose}
      footer={duplicate ? (
        <>
          <button className="btn" onClick={() => setDuplicate(null)}>Go back</button>
          <button className="btn primary" disabled={save.isPending} onClick={() => save.mutate(true)}>It’s a separate payment, record it</button>
        </>
      ) : (
        <>
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={save.isPending || !isValidAmount(amount) || toPaise(amount) <= 0n || over}
            onClick={() => { setError(null); save.mutate(false) }}>
            {save.isPending ? 'Recording…' : `Record ${isValidAmount(amount) ? inr(amount) : 'payment'}`}
          </button>
        </>
      )}
    >
      {duplicate ? (
        <div className="notice warn" role="alert">{duplicate.message}</div>
      ) : (
        <>
          {error && <div className="notice error" role="alert">{error.message}</div>}
          <Field label="Cash received (₹)" error={over ? `More than the outstanding ${inr(loan.outstanding)}. Collect at most that amount.` : undefined}
            hint={partial ? 'Less than the instalment due: it will be recorded as a part payment.' : 'Applied to the oldest unpaid instalment first.'}>
            {(id) => <input id={id} className="input money" inputMode="decimal" value={amount} aria-invalid={over}
              onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ''))} />}
          </Field>
          <Field label="Note (optional)">
            {(id) => <input id={id} className="input" value={remarks} maxLength={255} onChange={(e) => setRemarks(e.target.value)}
              placeholder="e.g. paid by son at shop" />}
          </Field>
        </>
      )}
    </Modal>
  )
}

export function ReceiptSlip({ c }: { c: Collection }) {
  return (
    <div className="slip">
      <div className="row"><strong>{c.receipt_number}</strong><span className="spacer" /><StatusChip status={c.status} /></div>
      <div className="big" style={{ margin: '6px 0 10px' }}><Amount value={c.amount} /></div>
      <dl className="kv">
        <dt>Customer</dt><dd>{c.customer_name} ({c.customer_code})</dd>
        <dt>Loan</dt><dd>{c.loan_number}</dd>
        <dt>Collected</dt><dd>{fmtDateTime(c.collected_at)} by {c.agent_name}</dd>
        <dt>Applied to</dt>
        <dd>{c.allocations.length ? c.allocations.map((a) => `EMI ${a.installment_number} (${inr(a.amount)})`).join(', ') : '—'}</dd>
        <dt>Balance after</dt><dd><Amount value={c.loan_outstanding} /></dd>
        {c.remarks && <><dt>Note</dt><dd>{c.remarks}</dd></>}
        {c.void_reason && <><dt>Voided</dt><dd>{c.void_reason}</dd></>}
      </dl>
    </div>
  )
}

/* ------------------------------------------------------------------ hand cash over to the branch */
export function HandoverModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const inHand = useQuery({
    queryKey: ['collections', { status: 'COLLECTED', mine: true }],
    queryFn: () => get<Paginated<Collection>>('/collections/', { status: 'COLLECTED', page_size: 200, ordering: 'collected_at' }),
  })
  const rows = useMemo(() => inHand.data?.results ?? [], [inHand.data])
  const [selected, setSelected] = useState<Set<number> | null>(null)
  const chosen = selected ?? new Set(rows.map((r) => r.id))
  const expected = sum(rows.filter((r) => chosen.has(r.id)).map((r) => r.amount))
  const [declared, setDeclared] = useState<string | null>(null)
  const declaredValue = declared ?? expected
  const [notes, setNotes] = useState('')
  const [error, setError] = useState('')
  const gap = isValidAmount(declaredValue) ? subtract(expected, declaredValue) : '0'

  const toggle = (id: number) => {
    const next = new Set(chosen)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelected(next)
    setDeclared(null)
  }

  const submit = useMutation({
    mutationFn: () => post<Submission>('/submissions/', { collection_ids: [...chosen], declared_amount: declaredValue, notes }),
    onSuccess: (s) => {
      toast(`Hand-over ${s.submission_number} sent for counting`)
      qc.invalidateQueries()
      onClose()
    },
    onError: (e) => setError((e as Error).message),
  })

  return (
    <Modal wide title="Hand over cash to the branch"
      lede="Select the receipts whose cash you are handing over. The branch manager counts it and approves or rejects the hand-over."
      onClose={onClose}
      footer={<>
        <button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn primary" disabled={!chosen.size || submit.isPending || !isValidAmount(declaredValue) || (compare(gap, '0') !== 0 && !notes.trim())}
          onClick={() => submit.mutate()}>
          {submit.isPending ? 'Sending…' : `Hand over ${inr(declaredValue)}`}
        </button>
      </>}>
      {error && <div className="notice error" role="alert">{error}</div>}
      {inHand.isLoading ? <Loading /> : rows.length === 0 ? <Empty title="No cash in hand">Every receipt you collected has already been handed over.</Empty> : (
        <>
          <div className="table-wrap panel">
            <table className="data">
              <thead><tr><th><span className="sr-only">Include</span></th><th>Receipt</th><th>Customer</th><th>Collected</th><th className="right">Amount</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className={chosen.has(r.id) ? 'selected clickable' : 'clickable'} onClick={() => toggle(r.id)}>
                    <td><input type="checkbox" checked={chosen.has(r.id)} onChange={() => toggle(r.id)} onClick={(e) => e.stopPropagation()} aria-label={`Include ${r.receipt_number}`} /></td>
                    <td className="nowrap">{r.receipt_number}</td>
                    <td>{r.customer_name}</td>
                    <td className="nowrap">{fmtDate(r.collected_at)} {fmtTime(r.collected_at)}</td>
                    <td className="right"><Amount value={r.amount} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="form-grid">
            <Field label={`Receipts total (${chosen.size})`}>
              {(id) => <input id={id} className="input money" value={inr(expected)} readOnly />}
            </Field>
            <Field label="Cash you are handing over (₹)"
              error={compare(gap, '0') !== 0 ? `${compare(gap, '0') > 0 ? 'Short' : 'Over'} by ${inr(gap.replace('-', ''))}. Explain below.` : undefined}>
              {(id) => <input id={id} className="input money" inputMode="decimal" value={declaredValue}
                onChange={(e) => setDeclared(e.target.value.replace(/[^\d.]/g, ''))} />}
            </Field>
            <Field label="Note for the branch manager" className="full">
              {(id) => <input id={id} className="input" value={notes} maxLength={255} onChange={(e) => setNotes(e.target.value)} />}
            </Field>
          </div>
        </>
      )}
    </Modal>
  )
}
