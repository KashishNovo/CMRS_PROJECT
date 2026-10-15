import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { Field } from '../components/ui'

const DEMO = import.meta.env.VITE_SHOW_DEMO_LOGINS !== 'false'
const DEMO_PASSWORD = 'Cmrs@2026'
const DEMO_USERS = [
  { username: 'agent.ravi', who: 'Collection agent', where: 'Mumbai' },
  { username: 'manager.mum', who: 'Branch manager', where: 'Mumbai' },
  { username: 'finance', who: 'Finance', where: 'All branches' },
  { username: 'admin', who: 'Administrator', where: 'All branches' },
]

const STAGES = [
  ['var(--stage-agent)', 'Customer pays agent'],
  ['var(--stage-count)', 'Agent hands over'],
  ['var(--stage-branch)', 'Branch counts'],
  ['var(--stage-bank)', 'Banked'],
  ['var(--stage-settled)', 'Credited'],
]

export default function Login() {
  const { user, login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to="/" replace />

  async function submit(e: FormEvent, u = username, p = password) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await login(u.trim(), p)
    } catch (err) {
      setError(err instanceof Error && 'status' in err && (err as { status: number }).status === 401
        ? 'That username and password don’t match an active account.'
        : err instanceof Error ? err.message : 'Sign-in failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <section className="login-art">
        <div className="brand" style={{ padding: 0 }}>
          <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
            <path d="M8 11h16M8 16h16M8 21h10" stroke="#E0A526" strokeWidth="2.6" strokeLinecap="round" />
          </svg>
          <div className="brand-name">CMRS</div>
        </div>
        <div>
          <h1>Every rupee collected, accounted for until it reaches the bank.</h1>
          <p>
            Record field repayments, verify cash at the branch, bank it and match it against the statement,
            with every shortfall caught at the stage where it happened.
          </p>
        </div>
        <div className="route" aria-label="Cash lifecycle">
          {STAGES.map(([c, label]) => <div key={label} style={{ ['--c' as string]: c }}>{label}</div>)}
        </div>
      </section>
      <section className="login-form">
        <form onSubmit={submit} noValidate>
          <div>
            <h2>Sign in</h2>
            <p className="muted small">Use the account your branch or head office gave you.</p>
          </div>
          {error && <div className="notice error" role="alert">{error}</div>}
          <Field label="Username">
            {(id) => <input id={id} className="input" autoComplete="username" value={username}
              onChange={(e) => setUsername(e.target.value)} required />}
          </Field>
          <Field label="Password">
            {(id) => <input id={id} className="input" type="password" autoComplete="current-password" value={password}
              onChange={(e) => setPassword(e.target.value)} required />}
          </Field>
          <button className="btn primary" disabled={busy || !username || !password}>{busy ? 'Signing in…' : 'Sign in'}</button>
          {DEMO && (
            <div className="demo">
              <p className="small muted">Demo accounts (password {DEMO_PASSWORD})</p>
              <div className="demo-grid">
                {DEMO_USERS.map((d) => (
                  <button type="button" key={d.username} disabled={busy}
                    onClick={(e) => { setUsername(d.username); setPassword(DEMO_PASSWORD); submit(e, d.username, DEMO_PASSWORD) }}>
                    <b>{d.who}</b>
                    <span className="muted">{d.username} · {d.where}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </form>
      </section>
    </div>
  )
}
