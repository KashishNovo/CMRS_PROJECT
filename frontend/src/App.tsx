import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import type { Role } from './api/types'
import { useAuth } from './auth/AuthContext'
import Layout from './components/Layout'
import { Empty, Loading } from './components/ui'
import { Branches, Users } from './pages/Admin'
import Audit from './pages/Audit'
import Collections from './pages/Collections'
import CustomerDetail from './pages/CustomerDetail'
import Customers from './pages/Customers'
import Dashboard from './pages/Dashboard'
import Deposits from './pages/Deposits'
import Discrepancies from './pages/Discrepancies'
import Login from './pages/Login'
import MyDay from './pages/MyDay'
import Reports from './pages/Reports'
import Submissions from './pages/Submissions'

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <Loading label="Checking your session…" />
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

/** UI-level guard only; the API enforces the same rules independently. */
function Only({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { hasRole } = useAuth()
  return hasRole(...roles) ? <>{children}</> : <Empty title="Not available for your role">Ask an administrator if you need access.</Empty>
} 

function Home() {
  const { user } = useAuth()
  return user?.role === 'AGENT' ? <MyDay /> : <Dashboard />
}

const REVIEWERS: Role[] = ['ADMIN', 'FINANCE', 'BRANCH_MANAGER']

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<RequireAuth><Layout /></RequireAuth>}>
        <Route index element={<Home />} />
        <Route path="customers" element={<Customers />} />
        <Route path="customers/:id" element={<CustomerDetail />} />
        <Route path="collections" element={<Collections />} />
        <Route path="submissions" element={<Submissions />} />
        <Route path="deposits" element={<Only roles={REVIEWERS}><Deposits /></Only>} />
        <Route path="discrepancies" element={<Discrepancies />} />
        <Route path="reports" element={<Only roles={REVIEWERS}><Reports /></Only>} />
        <Route path="audit" element={<Only roles={REVIEWERS}><Audit /></Only>} />
        <Route path="users" element={<Only roles={['ADMIN']}><Users /></Only>} />
        <Route path="branches" element={<Only roles={['ADMIN']}><Branches /></Only>} />
        <Route path="*" element={<Empty title="Page not found">Use the menu to find your way back.</Empty>} />
      </Route>
    </Routes>
  )
}
