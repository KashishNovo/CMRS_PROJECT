import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { get } from '../api/client'
import type { AgentSummaryRow, BranchSummaryRow, Dashboard as DashboardData } from '../api/types'
import { useUser } from '../auth/AuthContext'
import FilterBar from '../components/FilterBar'
import { Amount, Empty, ErrorNotice, Loading, PageHeader, Panel } from '../components/ui'
import { fmtDate, isoDate, monthStart } from '../lib/format'
import { useFilters } from '../lib/hooks'
import { inr, toPaise } from '../lib/money'

const STAGE_COLOR: Record<string, string> = {
  COLLECTED: 'var(--stage-agent)',
  SUBMITTED: 'var(--stage-count)',
  BRANCH_RECEIVED: 'var(--stage-branch)',
  DEPOSITED: 'var(--stage-bank)',
  SETTLED: 'var(--stage-settled)',
}
const STAGE_LABEL: Record<string, string> = {
  COLLECTED: 'Still with agents',
  SUBMITTED: 'Awaiting branch count',
  BRANCH_RECEIVED: 'In branch safe',
  DEPOSITED: 'Deposited, awaiting credit',
  SETTLED: 'Credited to company',
}
const COLLECTION_STATUSES = Object.entries(STAGE_LABEL).map(([value, label]) => ({ value, label }))

/** Chart axes need numbers; these are display-only conversions, never used for arithmetic. */
const chartNumber = (v: string) => Number(toPaise(v)) / 100

export default function Dashboard() {
  const user = useUser()
  const f = useFilters({ date_from: monthStart(), date_to: isoDate(), branch: '', agent: '', status: '' })
  const params = f.filters
  const dash = useQuery({ queryKey: ['dashboard', params], queryFn: () => get<DashboardData>('/reports/dashboard/', params) })
  const global = user.role === 'ADMIN' || user.role === 'FINANCE'
  const branches = useQuery({
    queryKey: ['branch-summary', params],
    queryFn: () => get<{ results: BranchSummaryRow[] }>('/reports/branches/', params),
    enabled: global,
  })
  const agents = useQuery({
    queryKey: ['agent-summary', params],
    queryFn: () => get<{ results: AgentSummaryRow[] }>('/reports/agents/', params),
    enabled: !global,
  })

  const d = dash.data
  return (
    <div className="stack">
      <PageHeader
        title="Where the cash is"
        lede={global
          ? 'Live position of collected cash across all branches, and what moved during the selected period.'
          : `Live position of collected cash at ${user.branch_detail?.name}, and what moved during the selected period.`}
      />
      <FilterBar filters={f.filters} set={f.set} statuses={COLLECTION_STATUSES} />
      <ErrorNotice error={dash.error} />
      {!d ? <Loading /> : (
        <>
          <MoneyTrail d={d} />

          <Panel title="This period" sub={`${fmtDate(d.filters.date_from)} to ${fmtDate(d.filters.date_to)}`} flush>
            <dl className="figures">
              <div className="figure">
                <dt>Instalments falling due</dt>
                <dd><Amount value={d.flow.expected} /></dd>
                <div className="delta">
                  {d.flow.collection_efficiency ? `${d.flow.collection_efficiency}% of it paid so far` : 'Nothing due in range'}
                </div>
              </div>
              <div className="figure">
                <dt>Collected by agents</dt>
                <dd><Amount value={d.flow.collected} /></dd>
                <div className="delta">{d.flow.collected_count} receipts</div>
              </div>
              <div className="figure">
                <dt>Counted at branches / deposited</dt>
                <dd><Amount value={d.flow.received_at_branch} /></dd>
                <div className="delta"><Amount value={d.flow.deposited} /> banked</div>
              </div>
              <div className="figure">
                <dt>Loan book outstanding</dt>
                <dd><Amount value={d.position.outstanding} /></dd>
                <div className="delta">{d.position.active_loans} active loans</div>
              </div>
            </dl>
            <div className="panel-body" style={{ borderTop: '1px solid var(--rule)' }}>
              <Lifecycle d={d} />
            </div>
          </Panel>

          <div className="grid-2">
            <Panel title="Daily collections" sub="Bars: collected. Line: instalments falling due.">
              <Trend d={d} />
            </Panel>
            <Discrepancies d={d} />
          </div>

          {global ? <BranchTable rows={branches.data?.results} /> : <AgentTable rows={agents.data?.results} />}
        </>
      )}
    </div>
  )
}

function MoneyTrail({ d }: { d: DashboardData }) {
  const p = d.position
  const stations = [
    { c: 'var(--stage-agent)', where: 'With agents', value: p.cash_with_agents, note: 'Collected, not yet handed over', to: '/collections?status=COLLECTED' },
    { c: 'var(--stage-count)', where: 'Awaiting count', value: p.pending_verification, note: 'Handed over, manager to verify', to: '/submissions?status=PENDING' },
    { c: 'var(--stage-branch)', where: 'In branch safe', value: p.cash_at_branch, note: 'Verified, not yet banked', to: '/deposits' },
    {
      c: 'var(--stage-bank)', where: 'In transit to bank', value: p.in_transit_to_bank,
      note: p.delayed_deposits ? `${p.delayed_deposits} deposit${p.delayed_deposits > 1 ? 's' : ''} past settlement SLA` : 'Deposited, awaiting credit',
      warn: p.delayed_deposits > 0, to: '/deposits?status=PENDING_SETTLEMENT',
    },
    { c: 'var(--stage-settled)', where: 'Credited this period', value: d.flow.settled, note: 'Matched to bank statement', to: '/deposits?status=SETTLED' },
  ]
  return (
    <section className="trail" aria-label="Cash position by custody stage">
      {stations.map((s) => (
        <Link key={s.where} to={s.to} className={`station ${s.warn ? 'warn' : ''}`} style={{ ['--c' as string]: s.c, color: 'inherit', textDecoration: 'none' }}>
          <div className="where">{s.where}</div>
          <div className="value"><Amount value={s.value} /></div>
          <div className="note">{s.note}</div>
        </Link>
      ))}
    </section>
  )
}

function Lifecycle({ d }: { d: DashboardData }) {
  const total = toPaise(d.flow.collected)
  if (total === 0n) return <p className="muted">No receipts in this period.</p>
  return (
    <div>
      <h3 style={{ marginBottom: 10 }}>How far this period’s collections have travelled</h3>
      <div className="lifecycle" role="img" aria-label="Share of collected cash at each stage">
        {d.lifecycle.map((s) => {
          const pct = Number((toPaise(s.at_stage) * 10000n) / total) / 100
          return pct > 0 ? <span key={s.stage} style={{ width: `${pct}%`, background: STAGE_COLOR[s.stage] }} title={`${STAGE_LABEL[s.stage]}: ${inr(s.at_stage)}`} /> : null
        })}
      </div>
      <div className="legend">
        {d.lifecycle.map((s) => (
          <span key={s.stage}><i style={{ background: STAGE_COLOR[s.stage] }} />{STAGE_LABEL[s.stage]} <Amount value={s.at_stage} /></span>
        ))}
      </div>
    </div>
  )
}

function Trend({ d }: { d: DashboardData }) {
  const data = d.trend.map((t) => ({
    day: new Date(t.date + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }),
    collected: chartNumber(t.collected),
    expected: chartNumber(t.expected),
    raw: t,
  }))
  if (!data.length) return <Empty title="No days in range" />
  return (
    <div style={{ width: '100%', height: 260 }}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="#e4e8ef" />
          <XAxis dataKey="day" tick={{ fontSize: 11, fill: '#5b6578' }} tickLine={false} axisLine={{ stroke: '#d9dee7' }} interval="preserveStartEnd" minTickGap={14} />
          <YAxis tick={{ fontSize: 11, fill: '#5b6578' }} tickLine={false} axisLine={false} width={64}
            tickFormatter={(v: number) => inr(String(v), { compact: true })} />
          <Tooltip
            formatter={(_v, name, item) => [inr((item.payload as { raw: { collected: string; expected: string } }).raw[name === 'collected' ? 'collected' : 'expected']), name === 'collected' ? 'Collected' : 'Falling due']}
            contentStyle={{ borderRadius: 8, borderColor: '#d9dee7', fontSize: 13 }}
          />
          <Bar dataKey="collected" fill="var(--stage-agent)" radius={[3, 3, 0, 0]} maxBarSize={22} />
          <Line dataKey="expected" stroke="var(--ink)" strokeWidth={1.6} dot={false} type="stepAfter" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

function Discrepancies({ d }: { d: DashboardData }) {
  const x = d.discrepancies
  const stageName: Record<string, string> = { SUBMISSION: 'Agent → branch', DEPOSIT: 'Branch → bank', SETTLEMENT: 'Bank → company account' }
  return (
    <Panel title="Open discrepancies" sub="Raised automatically whenever two figures should agree and don’t."
      actions={<Link to="/discrepancies?status=OPEN" className="btn small">Review</Link>}>
      {x.open_count === 0 ? (
        <Empty title="Nothing to reconcile">Every count, deposit and bank credit matches.</Empty>
      ) : (
        <div className="stack">
          <div className="compare">
            <div><div className="k">Open items</div><div className="v">{x.open_count}</div></div>
            <div className="diff-short"><div className="k">Cash short</div><div className="v"><Amount value={x.open_shortage} /></div></div>
            <div className="diff-excess"><div className="k">Cash excess</div><div className="v"><Amount value={x.open_excess} /></div></div>
          </div>
          <table className="data">
            <thead><tr><th>Where it happened</th><th className="right">Items</th><th className="right">Amount</th></tr></thead>
            <tbody>
              {x.by_stage.map((s) => (
                <tr key={s.stage}><td>{stageName[s.stage] ?? s.stage}</td><td className="right">{s.count}</td><td className="right"><Amount value={s.amount} /></td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  )
}

function BranchTable({ rows }: { rows?: BranchSummaryRow[] }) {
  return (
    <Panel title="By branch" flush>
      {!rows ? <Loading /> : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Branch</th><th className="right">Collected</th><th className="right">With agents</th>
                <th className="right">Awaiting count</th><th className="right">In safe</th><th className="right">Deposited</th>
                <th className="right">Credited</th><th className="right">Open discrepancies</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.branch}>
                  <td><strong>{r.code}</strong><span className="sub">{r.name}</span></td>
                  <td className="right"><Amount value={r.collected} /><span className="sub">{r.receipts} receipts</span></td>
                  <td className="right"><Amount value={r.cash_with_agents} /></td>
                  <td className="right"><Amount value={r.pending_verification} /></td>
                  <td className="right"><Amount value={r.cash_at_branch} /></td>
                  <td className="right"><Amount value={r.deposited} /></td>
                  <td className="right"><Amount value={r.settled} /></td>
                  <td className="right">{r.open_discrepancies ? <><span className="chip alert">{r.open_discrepancies}</span><span className="sub"><Amount value={r.open_discrepancy_amount} /></span></> : <span className="muted">None</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  )
}

export function AgentTable({ rows }: { rows?: AgentSummaryRow[] }) {
  return (
    <Panel title="By agent" flush>
      {!rows ? <Loading /> : rows.length === 0 ? <Empty title="No agents" /> : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Agent</th><th className="right">Customers</th><th className="right">Falling due</th>
                <th className="right">Collected</th><th className="right">Cash in hand</th><th className="right">Awaiting count</th>
                <th className="right">Open shortage</th><th className="right">Rejected hand-overs</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.agent}>
                  <td><strong>{r.name}</strong><span className="sub">{r.branch_code}</span></td>
                  <td className="right">{r.assigned_customers}</td>
                  <td className="right"><Amount value={r.expected} /></td>
                  <td className="right"><Amount value={r.collected} /><span className="sub">{r.receipts} receipts</span></td>
                  <td className="right"><Amount value={r.cash_in_hand} /></td>
                  <td className="right"><Amount value={r.pending_verification} /></td>
                  <td className="right">{toPaise(r.open_shortage) > 0n ? <span className="chip alert">{inr(r.open_shortage)}</span> : <span className="muted">None</span>}</td>
                  <td className="right">{r.rejected_submissions || <span className="muted">0</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  )
}
