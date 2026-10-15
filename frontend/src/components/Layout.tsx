import { useState, type ReactNode } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { get } from '../api/client'
import type { Paginated, Role } from '../api/types'
import { useAuth, useUser } from '../auth/AuthContext'

const I = {
  dash: <path d="M3 13h7V3H3zM14 21h7V11h-7zM3 21h7v-4H3zM14 7h7V3h-7z" />,
  day: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5" /></>,
  people: <><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5M16 4.5a3.5 3.5 0 010 7M18 14.8c2 .7 3.2 2.5 3.6 5.2" /></>,
  receipt: <path d="M6 2h12v20l-3-2-3 2-3-2-3 2zM9 7h6M9 11h6M9 15h4" />,
  handover: <><path d="M3 15h4l3 2h5a2 2 0 000-4h-3" /><path d="M7 15V9l4-2h3l5 4v4" /><rect x="14" y="2" width="7" height="5" rx="1" /></>,
  bank: <path d="M3 10l9-6 9 6M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 21h18" />,
  alert: <><path d="M12 3l10 18H2z" /><path d="M12 10v5M12 18v.5" /></>,
  report: <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />,
  audit: <><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" /><path d="M8.5 12l2.5 2.5 4.5-5" /></>,
  users: <><circle cx="12" cy="8" r="4" /><path d="M4 21c1-4 4.2-6 8-6s7 2 8 6" /></>,
  branch: <path d="M4 21V8l8-5 8 5v13M9 21v-6h6v6" />,
}

function Icon({ name }: { name: keyof typeof I }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {I[name]}
    </svg>
  )
}

interface Item { to: string; label: string; icon: keyof typeof I; roles: Role[]; badge?: ReactNode }

function useCounts(role: Role) {
  const pendingSubs = useQuery({
    queryKey: ['count', 'submissions-pending'],
    queryFn: () => get<Paginated<unknown>>('/submissions/', { status: 'PENDING', page_size: 1 }),
    enabled: role === 'BRANCH_MANAGER' || role === 'ADMIN',
    refetchInterval: 60_000,
  })
  const pendingDeps = useQuery({
    queryKey: ['count', 'deposits-pending'],
    queryFn: () => get<Paginated<unknown>>('/deposits/', { status: 'PENDING_SETTLEMENT', page_size: 1 }),
    enabled: role === 'FINANCE' || role === 'ADMIN',
    refetchInterval: 60_000,
  })
  const openDisc = useQuery({
    queryKey: ['count', 'discrepancies-open'],
    queryFn: () => get<Paginated<unknown>>('/discrepancies/', { status: 'OPEN', page_size: 1 }),
    enabled: role !== 'AGENT',
    refetchInterval: 60_000,
  })
  return { subs: pendingSubs.data?.count, deps: pendingDeps.data?.count, disc: openDisc.data?.count }
}

export default function Layout() {
  const user = useUser()
  const { logout } = useAuth()
  const [open, setOpen] = useState(false)
  const location = useLocation()
  const counts = useCounts(user.role)
  const badge = (n?: number, soft = false) => (n ? <span className={`badge ${soft ? 'soft' : ''}`}>{n}</span> : null)

  const groups: { title?: string; items: Item[] }[] = [
    {
      items: [
        { to: '/', label: 'Dashboard', icon: 'dash', roles: ['ADMIN', 'FINANCE', 'BRANCH_MANAGER'] },
        { to: '/', label: 'My day', icon: 'day', roles: ['AGENT'] },
      ],
    },
    {
      title: 'Cash trail',
      items: [
        { to: '/customers', label: user.role === 'AGENT' ? 'My customers' : 'Customers & loans', icon: 'people', roles: ['ADMIN', 'BRANCH_MANAGER', 'AGENT', 'FINANCE'] },
        { to: '/collections', label: 'Receipts', icon: 'receipt', roles: ['ADMIN', 'FINANCE', 'BRANCH_MANAGER', 'AGENT'] },
        { to: '/submissions', label: user.role === 'AGENT' ? 'My hand-overs' : 'Cash hand-overs', icon: 'handover', roles: ['ADMIN', 'BRANCH_MANAGER', 'AGENT', 'FINANCE'], badge: badge(counts.subs, true) },
        { to: '/deposits', label: user.role === 'FINANCE' ? 'Settlements' : 'Bank deposits', icon: 'bank', roles: ['ADMIN', 'FINANCE', 'BRANCH_MANAGER'], badge: badge(counts.deps, true) },
        { to: '/discrepancies', label: 'Discrepancies', icon: 'alert', roles: ['ADMIN', 'FINANCE', 'BRANCH_MANAGER', 'AGENT'], badge: badge(counts.disc) },
      ],
    },
    {
      title: 'Oversight',
      items: [
        { to: '/reports', label: 'Branch & agent reports', icon: 'report', roles: ['ADMIN', 'FINANCE', 'BRANCH_MANAGER'] },
        { to: '/audit', label: 'Audit trail', icon: 'audit', roles: ['ADMIN', 'FINANCE', 'BRANCH_MANAGER'] },
        { to: '/users', label: 'Users', icon: 'users', roles: ['ADMIN'] },
        { to: '/branches', label: 'Branches', icon: 'branch', roles: ['ADMIN'] },
      ],
    },
  ]

  return (
    <div className={`shell ${open ? 'nav-open' : ''}`} data-path={location.pathname}>
      <div className="topbar">
        <button onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-controls="sidebar">Menu</button>
        <strong>CMRS</strong>
      </div>
      <aside className="sidebar" id="sidebar" onClick={(e) => (e.target as HTMLElement).closest('a') && setOpen(false)}>
        <div className="brand">
          <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
            <rect width="32" height="32" rx="7" fill="#fff" fillOpacity=".1" />
            <path d="M8 11h16M8 16h16M8 21h10" stroke="#E0A526" strokeWidth="2.6" strokeLinecap="round" />
          </svg>
          <div>
            <div className="brand-name">CMRS</div>
            <div className="brand-sub">Cash management & reconciliation</div>
          </div>
        </div>
        <nav className="nav" aria-label="Main">
          {groups.map((g, gi) => {
            const items = g.items.filter((i) => i.roles.includes(user.role))
            if (!items.length) return null
            return (
              <div key={gi} className="nav">
                {g.title && <div className="nav-group">{g.title}</div>}
                {items.map((i) => (
                  <NavLink key={i.label} to={i.to} end={i.to === '/'}>
                    <Icon name={i.icon} />
                    {i.label}
                    {i.badge}
                  </NavLink>
                ))}
              </div>
            )
          })}
        </nav>
        <div className="sidebar-foot">
          <div className="who">{user.full_name}</div>
          <div className="who-role">
            {user.role_display}
            {user.branch_detail ? `, ${user.branch_detail.name}` : ', all branches'}
          </div>
          <button className="link-btn" onClick={logout}>Sign out</button>
        </div>
      </aside>
      <main className="main" id="main">
        <Outlet />
      </main>
    </div>
  )
}
