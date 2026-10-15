import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { get } from '../api/client'
import type { Collection, DailySummary, Loan, Paginated } from '../api/types'
import { useUser } from '../auth/AuthContext'
import { HandoverModal, ReceiptSlip, RecordPaymentModal } from '../components/AgentModals'
import { Amount, Empty, Loading, Modal, PageHeader, Panel, StatusChip } from '../components/ui'
import { fmtDate, fmtTime, isoDate } from '../lib/format'

/** The collection agent's home: what is due, what they hold, and handing it over. */
export default function MyDay() {
  const user = useUser()
  const [paying, setPaying] = useState<Loan | null>(null)
  const [handover, setHandover] = useState(false)
  const [viewing, setViewing] = useState<Collection | null>(null)
  const summary = useQuery({ queryKey: ['daily-summary'], queryFn: () => get<DailySummary>('/collections/daily-summary/') })
  const loans = useQuery({
    queryKey: ['loans', 'mine-active'],
    queryFn: () => get<Paginated<Loan>>('/loans/', { status: 'ACTIVE', page_size: 200 }),
  })
  const today = useQuery({
    queryKey: ['collections', 'today'],
    queryFn: () => get<Paginated<Collection>>('/collections/', { date_from: isoDate(), date_to: isoDate(), page_size: 100 }),
  })

  const horizon = new Date()
  horizon.setDate(horizon.getDate() + 7)
  const due = (loans.data?.results ?? [])
    .filter((l) => l.next_due_date && new Date(l.next_due_date) <= horizon)
    .sort((a, b) => (a.next_due_date ?? '').localeCompare(b.next_due_date ?? ''))
  const s = summary.data

  return (
    <div className="stack">
      <PageHeader title={`Good ${new Date().getHours() < 12 ? 'morning' : new Date().getHours() < 17 ? 'afternoon' : 'evening'}, ${user.first_name}`}
        lede={`${fmtDate(isoDate())}, ${user.branch_detail?.name}`}
        actions={<button className="btn primary" onClick={() => setHandover(true)} disabled={!s || s.cash_in_hand_receipts === 0}>Hand over cash</button>} />

      <section className="trail" style={{ gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' }} aria-label="Today">
        <div className="station" style={{ ['--c' as string]: 'var(--ink)' }}>
          <div className="where">Collected today</div>
          <div className="value">{s ? <Amount value={s.collected_amount} /> : '…'}</div>
          <div className="note">{s?.collected_count ?? 0} receipts</div>
        </div>
        <div className="station" style={{ ['--c' as string]: 'var(--stage-agent)' }}>
          <div className="where">Cash in your hand</div>
          <div className="value">{s ? <Amount value={s.cash_in_hand} /> : '…'}</div>
          <div className="note">{s?.cash_in_hand_receipts ?? 0} receipts to hand over</div>
        </div>
        <div className="station" style={{ ['--c' as string]: 'var(--stage-count)' }}>
          <div className="where">Awaiting branch count</div>
          <div className="value">{s ? <Amount value={s.pending_verification} /> : '…'}</div>
          <div className="note"><Link to="/submissions">See your hand-overs</Link></div>
        </div>
      </section>

      <div className="grid-2">
        <Panel title="Due this week" sub="Your customers with an instalment due or overdue, oldest first." flush>
          {loans.isLoading ? <Loading /> : due.length === 0 ? <Empty title="Nothing due">No instalments due in the next 7 days.</Empty> : (
            <div className="table-wrap">
              <table className="data">
                <thead><tr><th>Customer</th><th>Due</th><th className="right">Amount</th><th /></tr></thead>
                <tbody>
                  {due.map((l) => {
                    const overdue = l.next_due_date! < isoDate()
                    return (
                      <tr key={l.id}>
                        <td><Link to={`/customers/${l.customer}`}>{l.customer_name}</Link><span className="sub">{l.loan_number}</span></td>
                        <td className="nowrap">{overdue ? <span className="chip alert">Overdue {fmtDate(l.next_due_date)}</span> : fmtDate(l.next_due_date)}</td>
                        <td className="right"><Amount value={l.next_due_amount} />{overdue && <span className="sub">arrears <Amount value={l.overdue_amount} /></span>}</td>
                        <td className="right"><button className="btn small primary" onClick={() => setPaying(l)}>Record payment</button></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="Today’s receipts" flush actions={<Link className="btn small" to="/customers">All customers</Link>}>
          {today.isLoading ? <Loading /> : !today.data?.results.length ? <Empty title="No receipts yet today">Record a payment from the list of dues.</Empty> : (
            <div className="table-wrap">
              <table className="data">
                <thead><tr><th>Time</th><th>Customer</th><th className="right">Amount</th><th>Status</th></tr></thead>
                <tbody>
                  {today.data.results.map((c) => (
                    <tr key={c.id} className="clickable" onClick={() => setViewing(c)}>
                      <td className="nowrap">{fmtTime(c.collected_at)}</td>
                      <td>{c.customer_name}<span className="sub">{c.receipt_number}</span></td>
                      <td className="right"><Amount value={c.amount} /></td>
                      <td><StatusChip status={c.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>

      {paying && <RecordPaymentModal loan={paying} onClose={() => setPaying(null)} />}
      {handover && <HandoverModal onClose={() => setHandover(false)} />}
      {viewing && (
        <Modal title="Receipt" onClose={() => setViewing(null)} footer={<button className="btn primary" onClick={() => setViewing(null)}>Close</button>}>
          <ReceiptSlip c={viewing} />
        </Modal>
      )}
    </div>
  )
}
