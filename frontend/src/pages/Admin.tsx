import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, patch, post } from '../api/client'
import type { Branch, Paginated, Role, User } from '../api/types'
import { Empty, Field, Loading, Modal, PageHeader, Panel, useFormError, useToast } from '../components/ui'
import { fmtDateTime } from '../lib/format'
import { useBranches } from '../lib/hooks'

const ROLES: { value: Role; label: string }[] = [
  { value: 'AGENT', label: 'Collection agent' },
  { value: 'BRANCH_MANAGER', label: 'Branch manager' },
  { value: 'FINANCE', label: 'Finance / Treasury' },
  { value: 'ADMIN', label: 'Administrator' },
]

export function Users() {
  const [editing, setEditing] = useState<User | 'new' | null>(null)
  const users = useQuery({ queryKey: ['users'], queryFn: () => get<Paginated<User>>('/users/', { page_size: 200 }) })
  return (
    <div className="stack">
      <PageHeader title="Users" lede="Who can sign in, their role and which branch they work for."
        actions={<button className="btn primary" onClick={() => setEditing('new')}>Add user</button>} />
      <Panel flush>
        {users.isLoading ? <Loading /> : !users.data?.results.length ? <Empty title="No users" /> : (
          <div className="table-wrap">
            <table className="data">
              <thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Branch</th><th>Last sign-in</th><th>Status</th></tr></thead>
              <tbody>
                {users.data.results.map((u) => (
                  <tr key={u.id} className="clickable" onClick={() => setEditing(u)}>
                    <td><strong>{u.full_name}</strong><span className="sub">{u.email}</span></td>
                    <td>{u.username}</td>
                    <td>{u.role_display}</td>
                    <td>{u.branch_detail?.code ?? 'All branches'}</td>
                    <td className="nowrap">{fmtDateTime(u.last_login)}</td>
                    <td>{u.is_active ? <span className="chip settled">Active</span> : <span className="chip">Disabled</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      {editing && <UserForm user={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} />}
    </div>
  )
}

function UserForm({ user, onClose }: { user?: User; onClose: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const err = useFormError()
  const branches = useBranches()
  const [form, setForm] = useState({
    username: user?.username ?? '', first_name: user?.first_name ?? '', last_name: user?.last_name ?? '',
    email: user?.email ?? '', phone: user?.phone ?? '', role: user?.role ?? 'AGENT' as Role,
    branch: String(user?.branch ?? ''), is_active: user?.is_active ?? true, password: '',
  })
  const set = (p: Partial<typeof form>) => setForm((f) => ({ ...f, ...p }))
  const needsBranch = form.role === 'AGENT' || form.role === 'BRANCH_MANAGER'
  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = { ...form, branch: needsBranch ? form.branch || null : null }
      if (!form.password) delete body.password
      return user ? patch<User>(`/users/${user.id}/`, body) : post<User>('/users/', body)
    },
    onSuccess: () => { toast(user ? 'User updated' : 'User added'); qc.invalidateQueries({ queryKey: ['users'] }); qc.invalidateQueries({ queryKey: ['agents'] }); onClose() },
    onError: err.setError,
  })
  return (
    <Modal title={user ? `Edit ${user.full_name}` : 'Add user'} onClose={onClose} footer={<>
      <button className="btn ghost" onClick={onClose}>Cancel</button>
      <button className="btn primary" disabled={save.isPending} onClick={() => save.mutate()}>{user ? 'Save changes' : 'Add user'}</button>
    </>}>
      {err.banner}
      <div className="form-grid">
        <Field label="First name" error={err.field('first_name')}>{(id) => <input id={id} className="input" value={form.first_name} onChange={(e) => set({ first_name: e.target.value })} />}</Field>
        <Field label="Last name" error={err.field('last_name')}>{(id) => <input id={id} className="input" value={form.last_name} onChange={(e) => set({ last_name: e.target.value })} />}</Field>
        <Field label="Username" error={err.field('username')}>{(id) => <input id={id} className="input" value={form.username} onChange={(e) => set({ username: e.target.value })} autoComplete="off" />}</Field>
        <Field label="Email" error={err.field('email')}>{(id) => <input id={id} className="input" type="email" value={form.email} onChange={(e) => set({ email: e.target.value })} />}</Field>
        <Field label="Role" error={err.field('role')}>
          {(id) => <select id={id} className="select" value={form.role} onChange={(e) => set({ role: e.target.value as Role })}>{ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}</select>}
        </Field>
        <Field label="Branch" error={err.field('branch')} hint={needsBranch ? undefined : 'Finance and admins work across all branches.'}>
          {(id) => (
            <select id={id} className="select" value={needsBranch ? form.branch : ''} disabled={!needsBranch} onChange={(e) => set({ branch: e.target.value })}>
              <option value="">{needsBranch ? 'Choose a branch' : 'All branches'}</option>
              {branches.data?.map((b) => <option key={b.id} value={b.id}>{b.code} · {b.name}</option>)}
            </select>
          )}
        </Field>
        <Field label={user ? 'New password (leave blank to keep)' : 'Password'} error={err.field('password')} className="full" hint="At least 8 characters, not only numbers.">
          {(id) => <input id={id} className="input" type="password" value={form.password} onChange={(e) => set({ password: e.target.value })} autoComplete="new-password" />}
        </Field>
        {user && (
          <label className="check full"><input type="checkbox" checked={form.is_active} onChange={(e) => set({ is_active: e.target.checked })} /> Can sign in</label>
        )}
      </div>
    </Modal>
  )
}

export function Branches() {
  const [editing, setEditing] = useState<Branch | 'new' | null>(null)
  const branches = useBranches()
  return (
    <div className="stack">
      <PageHeader title="Branches" actions={<button className="btn primary" onClick={() => setEditing('new')}>Add branch</button>} />
      <Panel flush>
        {!branches.data ? <Loading /> : (
          <div className="table-wrap">
            <table className="data">
              <thead><tr><th>Code</th><th>Name</th><th>City</th><th>Status</th></tr></thead>
              <tbody>
                {branches.data.map((b) => (
                  <tr key={b.id} className="clickable" onClick={() => setEditing(b)}>
                    <td><strong>{b.code}</strong></td><td>{b.name}</td><td>{b.city}</td>
                    <td>{b.is_active ? <span className="chip settled">Active</span> : <span className="chip">Closed</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      {editing && <BranchForm branch={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} />}
    </div>
  )
}

function BranchForm({ branch, onClose }: { branch?: Branch; onClose: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const err = useFormError()
  const [form, setForm] = useState({ code: branch?.code ?? '', name: branch?.name ?? '', city: branch?.city ?? '', address: branch?.address ?? '', is_active: branch?.is_active ?? true })
  const set = (p: Partial<typeof form>) => setForm((f) => ({ ...f, ...p }))
  const save = useMutation({
    mutationFn: () => (branch ? patch(`/branches/${branch.id}/`, form) : post('/branches/', form)),
    onSuccess: () => { toast(branch ? 'Branch updated' : 'Branch added'); qc.invalidateQueries({ queryKey: ['branches'] }); onClose() },
    onError: err.setError,
  })
  return (
    <Modal title={branch ? `Edit ${branch.code}` : 'Add branch'} onClose={onClose} footer={<>
      <button className="btn ghost" onClick={onClose}>Cancel</button>
      <button className="btn primary" disabled={save.isPending || !form.code || !form.name} onClick={() => save.mutate()}>Save</button>
    </>}>
      {err.banner}
      <div className="form-grid">
        <Field label="Code" error={err.field('code')} hint="Used in receipt numbers, e.g. MUM01">{(id) => <input id={id} className="input" value={form.code} maxLength={10} onChange={(e) => set({ code: e.target.value.toUpperCase() })} />}</Field>
        <Field label="City" error={err.field('city')}>{(id) => <input id={id} className="input" value={form.city} onChange={(e) => set({ city: e.target.value })} />}</Field>
        <Field label="Name" className="full" error={err.field('name')}>{(id) => <input id={id} className="input" value={form.name} onChange={(e) => set({ name: e.target.value })} />}</Field>
        <Field label="Address" className="full">{(id) => <textarea id={id} className="textarea" value={form.address} onChange={(e) => set({ address: e.target.value })} />}</Field>
        {branch && <label className="check full"><input type="checkbox" checked={form.is_active} onChange={(e) => set({ is_active: e.target.checked })} /> Branch is operating</label>}
      </div>
    </Modal>
  )
}
