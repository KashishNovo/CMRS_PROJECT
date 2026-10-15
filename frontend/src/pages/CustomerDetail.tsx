import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { get, post } from '../api/client'
import type { Collection, Customer, Installment, Loan, Paginated } from '../api/types'
import { useUser } from '../auth/AuthContext'
import { RecordPaymentModal } from '../components/AgentModals'
import { Amount, Empty, ErrorNotice, Field, Loading, Modal, PageHeader, Panel, StatusChip, Tabs, useFormError, useToast } from '../components/ui'
import { fmtDate, fmtDateTime, isoDate } from '../lib/format'
import { inr, isValidAmount } from '../lib/money'
import { CustomerForm } from './Customers'

export default function CustomerDetail() {
  const { id } = useParams()
  const user = useUser()
  const canEdit = user.role === 'ADMIN' || user.role === 'BRANCH_MANAGER'
  const [editing, setEditing] = useState(false)
  const [newLoan, setNewLoan] = useState(false)
  const [loanId, setLoanId] = useState<number | null>(null)
  const customer = useQuery({ queryKey: ['customer', Number(id)], queryFn: () => get<Customer>(`/customers/${id}/`) })
  const loans = useQuery({
    queryKey: ['loans', { customer: id }],
    queryFn: () => get<Paginated<Loan>>('/loans/', { customer: id, page_size: 50 }),
  })
  const list = loans.data?.results ?? []
  const current = list.find((l) => l.id === loanId) ?? list.find((l) => l.status === 'ACTIVE') ?? list[0]

  if (customer.error) return <ErrorNotice error={customer.error} />
  if (!customer.data) return <Loading />
  const c = customer.data

  return (
    <div className="stack">
      <p className="small"><Link to="/customers">Customers</Link></p>
      <PageHeader title={c.full_name}
        lede={<>{c.customer_code} · {c.phone} · {c.branch_code} · collected by {c.assigned_agent_name ?? 'nobody yet'}{!c.is_active && <> · <span className="chip alert">Inactive</span></>}</>}
        actions={canEdit && <>
          <button className="btn" onClick={() => setEditing(true)}>Edit details</button>
          <button className="btn primary" onClick={() => setNewLoan(true)} disabled={!c.is_active}>Issue loan</button>
        </>} />
      {c.address && <p className="muted small" style={{ marginTop: -12 }}>{c.address}</p>}

      {loans.isLoading ? <Loading /> : list.length === 0 ? (
        <Panel><Empty title="No loans yet">{canEdit ? 'Issue a loan to generate its repayment schedule.' : null}</Empty></Panel>
      ) : (
        <>
          {list.length > 1 && (
            <Tabs value={String(current?.id)} onChange={(v) => setLoanId(Number(v))}
              items={list.map((l) => ({ value: String(l.id), label: `${l.loan_number}${l.status === 'CLOSED' ? ' (closed)' : ''}` }))} />
          )}
          {current && <LoanPanel loan={current} />}
        </>
      )}
      {editing && <CustomerForm customer={c} onClose={() => setEditing(false)} />}
      {newLoan && <LoanForm customer={c} onClose={() => setNewLoan(false)} onCreated={(l) => setLoanId(l.id)} />}
    </div>
  )
}

function LoanPanel({ loan }: { loan: Loan }) {
  const user = useUser()
  const [paying, setPaying] = useState(false)
  const [tab, setTab] = useState<'schedule' | 'history'>('schedule')
  const schedule = useQuery({ queryKey: ['schedule', loan.id], queryFn: () => get<Installment[]>(`/loans/${loan.id}/schedule/`) })
  const history = useQuery({ queryKey: ['repayments', loan.id], queryFn: () => get<Collection[]>(`/loans/${loan.id}/repayments/`) })

  return (
    <Panel title={`Loan ${loan.loan_number}`}
      sub={`${inr(loan.principal)} at ${loan.annual_interest_rate}% for ${loan.tenure_months} months, disbursed ${fmtDate(loan.disbursement_date)}`}
      actions={<>
        <StatusChip status={loan.status} />
        {user.role === 'AGENT' && loan.status === 'ACTIVE' && <button className="btn primary small" onClick={() => setPaying(true)}>Record payment</button>}
      </>}
      flush>
      <dl className="figures">
        <div className="figure"><dt>Monthly instalment</dt><dd><Amount value={loan.emi_amount} /></dd><div className="delta">Total payable <Amount value={loan.total_payable} /></div></div>
        <div className="figure"><dt>Repaid</dt><dd><Amount value={loan.total_paid} /></dd></div>
        <div className="figure"><dt>Outstanding</dt><dd><Amount value={loan.outstanding} /></dd>
          <div className="delta">{loan.next_due_date ? <>Next <Amount value={loan.next_due_amount} /> on {fmtDate(loan.next_due_date)}</> : 'Fully repaid'}</div></div>
        <div className="figure"><dt>Overdue</dt><dd style={{ color: loan.overdue_amount !== '0.00' ? 'var(--alert)' : undefined }}><Amount value={loan.overdue_amount} /></dd></div>
      </dl>
      <div className="panel-body" style={{ borderTop: '1px solid var(--rule)' }}>
        <Tabs value={tab} onChange={setTab} items={[
          { value: 'schedule', label: 'Repayment schedule' },
          { value: 'history', label: `Repayment history${history.data ? ` (${history.data.length})` : ''}` },
        ]} />
        {tab === 'schedule' ? (
          !schedule.data ? <Loading /> : (
            <div className="table-wrap">
              <table className="data">
                <thead><tr><th>EMI</th><th>Due</th><th className="right">Principal</th><th className="right">Interest</th><th className="right">Due</th><th className="right">Paid</th><th>Status</th></tr></thead>
                <tbody>
                  {schedule.data.map((i) => (
                    <tr key={i.installment_number}>
                      <td>{i.installment_number}</td>
                      <td className="nowrap">{fmtDate(i.due_date)}</td>
                      <td className="right"><Amount value={i.principal_component} /></td>
                      <td className="right"><Amount value={i.interest_component} /></td>
                      <td className="right"><Amount value={i.amount_due} /></td>
                      <td className="right"><Amount value={i.amount_paid} /></td>
                      <td>{i.is_overdue ? <span className="chip alert">{i.status === 'PARTIALLY_PAID' ? 'Part paid, overdue' : 'Overdue'}</span> : <StatusChip status={i.status!} label={i.status === 'PENDING' ? 'Upcoming' : undefined} />}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        ) : !history.data ? <Loading /> : history.data.length === 0 ? <Empty title="No repayments yet" /> : (
          <div className="table-wrap">
            <table className="data">
              <thead><tr><th>Receipt</th><th>Collected</th><th>Agent</th><th className="right">Amount</th><th>Where the cash is</th></tr></thead>
              <tbody>
                {history.data.map((r) => (
                  <tr key={r.id}>
                    <td className="nowrap">{r.receipt_number}</td>
                    <td className="nowrap">{fmtDateTime(r.collected_at)}</td>
                    <td>{r.agent_name}</td>
                    <td className="right"><Amount value={r.amount} />{r.void_reason && <span className="sub">{r.void_reason}</span>}</td>
                    <td><StatusChip status={r.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {paying && <RecordPaymentModal loan={loan} onClose={() => setPaying(false)} />}
    </Panel>
  )
}

interface Preview { emi_amount: string; total_payable: string; total_interest: string; installments: Installment[] }

function LoanForm({ customer, onClose, onCreated }: { customer: Customer; onClose: () => void; onCreated: (l: Loan) => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const err = useFormError()
  const [form, setForm] = useState({ principal: '50000', annual_interest_rate: '18', tenure_months: '12', disbursement_date: isoDate() })
  const set = (p: Partial<typeof form>) => setForm((f) => ({ ...f, ...p }))
  const [debounced, setDebounced] = useState(form)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(form), 350)
    return () => clearTimeout(t)
  }, [form])
  const valid = isValidAmount(debounced.principal) && isValidAmount(debounced.annual_interest_rate) && Number(debounced.tenure_months) > 0
  const preview = useQuery({
    queryKey: ['loan-preview', debounced],
    queryFn: () => post<Preview>('/loans/preview-schedule/', debounced),
    enabled: valid,
    retry: false,
  })
  const save = useMutation({
    mutationFn: () => post<Loan>('/loans/', { ...form, customer: customer.id }),
    onSuccess: (l) => {
      toast(`Loan ${l.loan_number} issued`)
      qc.invalidateQueries({ queryKey: ['loans'] })
      qc.invalidateQueries({ queryKey: ['customers'] })
      onCreated(l)
      onClose()
    },
    onError: err.setError,
  })

  return (
    <Modal wide title={`Issue a loan to ${customer.full_name}`} lede="Reducing-balance EMI. The full schedule is generated when you issue the loan."
      onClose={onClose} footer={<>
        <button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn primary" disabled={save.isPending || !preview.data} onClick={() => save.mutate()}>
          {save.isPending ? 'Issuing…' : 'Issue loan'}
        </button>
      </>}>
      {err.banner}
      <div className="form-grid" style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))' }}>
        <Field label="Principal (₹)" error={err.field('principal')}>
          {(id) => <input id={id} className="input" inputMode="decimal" value={form.principal} onChange={(e) => set({ principal: e.target.value.replace(/[^\d.]/g, '') })} />}
        </Field>
        <Field label="Interest % p.a." error={err.field('annual_interest_rate')}>
          {(id) => <input id={id} className="input" inputMode="decimal" value={form.annual_interest_rate} onChange={(e) => set({ annual_interest_rate: e.target.value.replace(/[^\d.]/g, '') })} />}
        </Field>
        <Field label="Tenure (months)" error={err.field('tenure_months')}>
          {(id) => <input id={id} className="input" inputMode="numeric" value={form.tenure_months} onChange={(e) => set({ tenure_months: e.target.value.replace(/\D/g, '') })} />}
        </Field>
        <Field label="Disbursed on" error={err.field('disbursement_date')}>
          {(id) => <input id={id} className="input" type="date" value={form.disbursement_date} onChange={(e) => set({ disbursement_date: e.target.value })} />}
        </Field>
      </div>
      {preview.error ? <ErrorNotice error={preview.error} /> : preview.data && (
        <>
          <div className="compare">
            <div><div className="k">Monthly instalment</div><div className="v"><Amount value={preview.data.emi_amount} /></div></div>
            <div><div className="k">Total interest</div><div className="v"><Amount value={preview.data.total_interest} /></div></div>
            <div><div className="k">Total payable</div><div className="v"><Amount value={preview.data.total_payable} /></div></div>
          </div>
          <div className="table-wrap panel" style={{ maxHeight: 240, overflow: 'auto' }}>
            <table className="data">
              <thead><tr><th>EMI</th><th>Due</th><th className="right">Principal</th><th className="right">Interest</th><th className="right">Amount</th></tr></thead>
              <tbody>
                {preview.data.installments.map((i) => (
                  <tr key={i.installment_number}>
                    <td>{i.installment_number}</td><td>{fmtDate(i.due_date)}</td>
                    <td className="right"><Amount value={i.principal_component} /></td>
                    <td className="right"><Amount value={i.interest_component} /></td>
                    <td className="right"><Amount value={i.amount_due} /></td>
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
