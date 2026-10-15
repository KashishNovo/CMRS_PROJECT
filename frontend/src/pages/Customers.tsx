import { useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { get, patch, post } from '../api/client'
import type { Customer, Paginated } from '../api/types'
import { useUser } from '../auth/AuthContext'
import { Amount, Empty, ErrorNotice, Field, Loading, Modal, PageHeader, Pager, Panel, useFormError, useToast } from '../components/ui'
import { useAgents, useBranches, useFilters } from '../lib/hooks'

export default function Customers() {
  const user = useUser()
  const navigate = useNavigate()
  const canEdit = user.role === 'ADMIN' || user.role === 'BRANCH_MANAGER'
  const global = user.role === 'ADMIN' || user.role === 'FINANCE'
  const f = useFilters({ search: '', branch: '', assigned_agent: '', is_active: 'true' })
  const [creating, setCreating] = useState(false)
  const branches = useBranches()
  const agents = useAgents(global ? f.filters.branch || null : user.branch, user.role !== 'AGENT')
  const list = useQuery({
    queryKey: ['customers', f.params],
    queryFn: () => get<Paginated<Customer>>('/customers/', f.params),
    placeholderData: keepPreviousData,
  })

  return (
    <div className="stack">
      <PageHeader title={user.role === 'AGENT' ? 'My customers' : 'Customers & loans'}
        lede={user.role === 'AGENT' ? 'Customers assigned to you for collection.' : 'Borrowers, their loans and repayment schedules.'}
        actions={canEdit && <button className="btn primary" onClick={() => setCreating(true)}>Add customer</button>} />
      <div className="filters" role="search">
        <Field label="Search" className="wide">
          {(id) => <input id={id} className="input" type="search" placeholder="Name, phone or customer code" value={f.filters.search}
            onChange={(e) => f.set({ search: e.target.value })} />}
        </Field>
        {global && (
          <Field label="Branch">
            {(id) => (
              <select id={id} className="select" value={f.filters.branch} onChange={(e) => f.set({ branch: e.target.value, assigned_agent: '' })}>
                <option value="">All branches</option>
                {branches.data?.map((b) => <option key={b.id} value={b.id}>{b.code}</option>)}
              </select>
            )}
          </Field>
        )}
        {user.role !== 'AGENT' && (
          <Field label="Agent">
            {(id) => (
              <select id={id} className="select" value={f.filters.assigned_agent} onChange={(e) => f.set({ assigned_agent: e.target.value })}>
                <option value="">All agents</option>
                {agents.data?.map((a) => <option key={a.id} value={a.id}>{a.full_name}</option>)}
              </select>
            )}
          </Field>
        )}
        <Field label="Show">
          {(id) => (
            <select id={id} className="select" value={f.filters.is_active} onChange={(e) => f.set({ is_active: e.target.value })}>
              <option value="true">Active customers</option>
              <option value="false">Inactive customers</option>
              <option value="">Everyone</option>
            </select>
          )}
        </Field>
      </div>
      <ErrorNotice error={list.error} />
      <Panel flush>
        {list.isLoading ? <Loading /> : !list.data?.results.length ? (
          <Empty title="No customers match">{canEdit ? 'Add a customer to issue their first loan.' : 'Try clearing the search.'}</Empty>
        ) : (
          <>
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr><th>Customer</th><th>Phone</th><th>Branch</th><th>Agent</th><th className="right">Active loans</th><th className="right">Outstanding</th></tr>
                </thead>
                <tbody>
                  {list.data.results.map((c) => (
                    <tr key={c.id} className="clickable" onClick={() => navigate(`/customers/${c.id}`)}>
                      <td><strong>{c.full_name}</strong><span className="sub">{c.customer_code}</span></td>
                      <td className="nowrap">{c.phone}</td>
                      <td>{c.branch_code}</td>
                      <td>{c.assigned_agent_name ?? <span className="chip alert">Unassigned</span>}</td>
                      <td className="right">{c.active_loans}</td>
                      <td className="right"><Amount value={c.outstanding} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager page={f.page} count={list.data.count} onPage={f.setPage} />
          </>
        )}
      </Panel>
      {creating && <CustomerForm onClose={() => setCreating(false)} onSaved={(c) => navigate(`/customers/${c.id}`)} />}
    </div>
  )
}

export function CustomerForm({ customer, onClose, onSaved }: { customer?: Customer; onClose: () => void; onSaved?: (c: Customer) => void }) {
  const user = useUser()
  const qc = useQueryClient()
  const toast = useToast()
  const branches = useBranches()
  const [form, setForm] = useState({
    full_name: customer?.full_name ?? '',
    phone: customer?.phone ?? '',
    email: customer?.email ?? '',
    address: customer?.address ?? '',
    id_number: customer?.id_number ?? '',
    branch: String(customer?.branch ?? user.branch ?? ''),
    assigned_agent: String(customer?.assigned_agent ?? ''),
    is_active: customer?.is_active ?? true,
  })
  const agents = useAgents(form.branch || null, !!form.branch)
  const err = useFormError()
  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }))

  const save = useMutation({
    mutationFn: () => {
      const body = { ...form, branch: form.branch || undefined, assigned_agent: form.assigned_agent || null }
      return customer ? patch<Customer>(`/customers/${customer.id}/`, body) : post<Customer>('/customers/', body)
    },
    onSuccess: (c) => {
      toast(customer ? 'Customer updated' : `Customer ${c.customer_code} added`)
      qc.invalidateQueries({ queryKey: ['customers'] })
      qc.invalidateQueries({ queryKey: ['customer', c.id] })
      onSaved?.(c)
      onClose()
    },
    onError: err.setError,
  })

  return (
    <Modal title={customer ? `Edit ${customer.full_name}` : 'Add customer'} onClose={onClose} footer={<>
      <button className="btn ghost" onClick={onClose}>Cancel</button>
      <button className="btn primary" disabled={save.isPending || !form.full_name || !form.phone} onClick={() => save.mutate()}>
        {save.isPending ? 'Saving…' : customer ? 'Save changes' : 'Add customer'}
      </button>
    </>}>
      {err.banner}
      <div className="form-grid">
        <Field label="Full name" className="full" error={err.field('full_name')}>
          {(id) => <input id={id} className="input" value={form.full_name} onChange={(e) => set({ full_name: e.target.value })} />}
        </Field>
        <Field label="Mobile number" error={err.field('phone')}>
          {(id) => <input id={id} className="input" inputMode="tel" value={form.phone} onChange={(e) => set({ phone: e.target.value })} />}
        </Field>
        <Field label="Email (optional)" error={err.field('email')}>
          {(id) => <input id={id} className="input" type="email" value={form.email} onChange={(e) => set({ email: e.target.value })} />}
        </Field>
        <Field label="Address" className="full" error={err.field('address')}>
          {(id) => <textarea id={id} className="textarea" value={form.address} onChange={(e) => set({ address: e.target.value })} />}
        </Field>
        <Field label="KYC / ID number" error={err.field('id_number')} hint="Store masked, e.g. XXXX-XXXX-1234">
          {(id) => <input id={id} className="input" value={form.id_number} onChange={(e) => set({ id_number: e.target.value })} />}
        </Field>
        {user.role === 'ADMIN' && (
          <Field label="Branch" error={err.field('branch')}>
            {(id) => (
              <select id={id} className="select" value={form.branch} onChange={(e) => set({ branch: e.target.value, assigned_agent: '' })}>
                <option value="">Choose a branch</option>
                {branches.data?.map((b) => <option key={b.id} value={b.id}>{b.code} · {b.name}</option>)}
              </select>
            )}
          </Field>
        )}
        <Field label="Collection agent" error={err.field('assigned_agent')}>
          {(id) => (
            <select id={id} className="select" value={form.assigned_agent} onChange={(e) => set({ assigned_agent: e.target.value })}>
              <option value="">Not assigned yet</option>
              {agents.data?.map((a) => <option key={a.id} value={a.id}>{a.full_name}</option>)}
            </select>
          )}
        </Field>
        {customer && (
          <label className="check full">
            <input type="checkbox" checked={form.is_active} onChange={(e) => set({ is_active: e.target.checked })} />
            Active customer (inactive customers can’t be issued new loans)
          </label>
        )}
      </div>
    </Modal>
  )
}
