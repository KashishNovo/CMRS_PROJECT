import { useQuery } from '@tanstack/react-query'
import { get } from '../api/client'
import type { AgentSummaryRow, BranchSummaryRow } from '../api/types'
import { useUser } from '../auth/AuthContext'
import FilterBar from '../components/FilterBar'
import { Amount, Loading, PageHeader, Panel } from '../components/ui'
import { isoDate, monthStart } from '../lib/format'
import { useFilters } from '../lib/hooks'
import { AgentTable } from './Dashboard'

export default function Reports() {
  const user = useUser()
  const f = useFilters({ date_from: monthStart(), date_to: isoDate(), branch: '', agent: '', status: '' })
  const params = f.filters
  const branches = useQuery({ queryKey: ['branch-summary', params], queryFn: () => get<{ results: BranchSummaryRow[] }>('/reports/branches/', params) })
  const agents = useQuery({ queryKey: ['agent-summary', params], queryFn: () => get<{ results: AgentSummaryRow[] }>('/reports/agents/', params) })

  function exportCsv() {
    const rows = agents.data?.results ?? []
    const head = ['Agent', 'Branch', 'Customers', 'Falling due', 'Collected', 'Receipts', 'Cash in hand', 'Awaiting count', 'Open shortage', 'Rejected hand-overs']
    const lines = rows.map((r) => [r.name, r.branch_code, r.assigned_customers, r.expected, r.collected, r.receipts, r.cash_in_hand, r.pending_verification, r.open_shortage, r.rejected_submissions])
    const csv = [head, ...lines].map((l) => l.map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`).join(',')).join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
    const a = Object.assign(document.createElement('a'), { href: url, download: `agent-summary-${params.date_from}-${params.date_to}.csv` })
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="stack">
      <PageHeader title="Branch & agent reports" lede="Collections and custody by branch and by agent for the selected period."
        actions={<button className="btn" onClick={exportCsv} disabled={!agents.data}>Download agent report (CSV)</button>} />
      <FilterBar filters={f.filters} set={f.set} />
      <Panel title={user.role === 'BRANCH_MANAGER' ? 'Branch summary' : 'By branch'} flush>
        {!branches.data ? <Loading /> : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr><th>Branch</th><th className="right">Collected</th><th className="right">With agents</th><th className="right">Awaiting count</th>
                  <th className="right">In safe</th><th className="right">Deposited</th><th className="right">Credited</th><th className="right">Open discrepancies</th></tr>
              </thead>
              <tbody>
                {branches.data.results.map((r) => (
                  <tr key={r.branch}>
                    <td><strong>{r.code}</strong><span className="sub">{r.name}</span></td>
                    <td className="right"><Amount value={r.collected} /><span className="sub">{r.receipts} receipts</span></td>
                    <td className="right"><Amount value={r.cash_with_agents} /></td>
                    <td className="right"><Amount value={r.pending_verification} /></td>
                    <td className="right"><Amount value={r.cash_at_branch} /></td>
                    <td className="right"><Amount value={r.deposited} /></td>
                    <td className="right"><Amount value={r.settled} /></td>
                    <td className="right">{r.open_discrepancies} <span className="sub"><Amount value={r.open_discrepancy_amount} /></span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <AgentTable rows={agents.data?.results} />
    </div>
  )
}
