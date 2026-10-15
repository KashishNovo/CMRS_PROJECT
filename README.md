# CMRS — Cash Management & Reconciliation System

A lending company's field agents collect loan repayments in cash. CMRS follows every rupee from the
customer to the company's bank account and flags the exact stage where money goes missing:

```
Customer ──► Collection agent ──► Branch ──► Bank deposit ──► Company account
 receipt      cash in hand        counted     slip + ref no.     statement credit
             COLLECTED  ──►  SUBMITTED ──► BRANCH_RECEIVED ──► DEPOSITED ──► SETTLED
```

| | |
|---|---|
| **Live app** | `https://<your-frontend>.vercel.app` — fill in after deploying (see [Deployment](#deployment)) |
| **API docs (Swagger)** | `https://<your-api>.onrender.com/api/docs/` |
| **Stack** | Django 5.2 · Django REST Framework · PostgreSQL 16 · React 19 + TypeScript (Vite) · JWT |
| **Tests** | 56 pytest tests covering every business case in the brief |

More detail: [Architecture & business rules](docs/ARCHITECTURE.md) · [API reference](docs/API.md) · [Video walkthrough script](docs/VIDEO_SCRIPT.md)

---

## Test credentials

Every demo account uses the password **`Cmrs@2026`**. The sign-in page also has one-click demo buttons.

| Role | Username | Scope | What to try |
|---|---|---|---|
| Collection agent | `agent.ravi` | Mumbai branch, own customers | *My day* → Record payment → Hand over cash |
| Collection agent | `agent.sneha`, `agent.amit`, `agent.pooja`, `agent.kiran` | Mumbai / Delhi / Bengaluru | |
| Branch manager | `manager.mum` | Mumbai branch | *Cash hand-overs* → Count → approve with a shortage; *Bank deposits* → Record deposit |
| Branch manager | `manager.del`, `manager.blr` | Delhi / Bengaluru | Delhi has a failed deposit; Bengaluru a delayed settlement |
| Finance | `finance` | All branches | *Settlements* → Match credit (exact, mismatch, or mark failed) |
| Administrator | `admin` | All branches + users | *Users*, *Branches*, Django admin at `/admin/` |

The seed data (`python manage.py seed_demo`) creates 3 branches, 70 customers with loans, and three weeks
of activity that exercises every edge case: partial payments, an agent shortage of ₹1,500 (resolved) and
another (open), an excess of ₹200, a rejected hand-over (suspected counterfeit notes) that was re-submitted,
a deposit slip ₹500 short of verified cash, a bank credit ₹100 short, a failed deposit that was re-banked,
a deposit past the settlement SLA, and cash still with agents and in branch safes today.

---

## Roles

| Role | Can do | Sees |
|---|---|---|
| **Agent** | Record repayments, void own un-handed-over receipts, hand cash to branch | Own assigned customers, own receipts and hand-overs |
| **Branch manager** | Manage branch customers & loans, count / approve / reject hand-overs, create bank deposits, resolve agent and deposit discrepancies | Own branch only |
| **Finance** | Confirm settlements against bank statement, mark deposits failed, resolve any discrepancy | All branches (read) |
| **Admin** | Everything above except recording cash (that is an agent's act), plus users and branches | All branches |

Separation of duties is deliberate: the person who handles cash (agent) can't verify it, the person who
verifies it (manager) can't confirm the bank credit, and Finance can't create the cash records it checks.

---

## Run locally

### Quickest — Windows, double-click

Needs only **Python 3.12+** and **Node.js LTS**. Double-click **`run-local.bat`** in the project folder. It
creates the virtual environment, installs packages, sets up a local SQLite database with demo data, starts
the backend (http://localhost:8000) and frontend (http://localhost:5173) in two windows, and opens the
browser. Close those two windows to stop the app. To use PostgreSQL instead, edit `backend\.env` and set
`DATABASE_URL=postgres://...` (SQLite is a local convenience only: the database-level triggers and the
test suite need PostgreSQL, and production runs on PostgreSQL).

### Option A — Docker (one command)

```bash
docker compose up --build
```
App: http://localhost:8080 · API docs: http://localhost:8080/api/docs/ · demo data is seeded on first start.

### Option B — without Docker

Prerequisites: Python 3.12+, Node 20+, PostgreSQL 14+.

```bash
# 1. Database
createdb cmrs

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # then edit DATABASE_URL if needed
export $(grep -v '^#' .env | xargs)
python manage.py migrate
python manage.py seed_demo      # demo branches, users, loans and 3 weeks of activity
python manage.py runserver      # http://localhost:8000

# 3. Frontend (new terminal)
cd frontend
npm install
npm run dev                     # http://localhost:5173 (proxies /api to :8000)
```

Reset demo data at any time with `python manage.py seed_demo --reset`.

### Tests

```bash
cd backend
pytest                          # needs DATABASE_URL pointing at a PostgreSQL server
```
PostgreSQL is required (not SQLite) because the tests also verify the database triggers and constraints.

---

## Environment variables

### Backend (`backend/.env.example`)

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | yes (prod) | dev key when `DJANGO_DEBUG=1` | Signs JWTs and sessions. App refuses to start without it in production. |
| `DJANGO_DEBUG` | no | `0` | `1` for local development only |
| `DATABASE_URL` | yes | `postgres://postgres:postgres@localhost:5432/cmrs` | PostgreSQL connection string, or `sqlite` for the local quick-start |
| `DJANGO_ALLOWED_HOSTS` | yes (prod) | `localhost,127.0.0.1` | Comma-separated. Render's hostname is added automatically. |
| `CORS_ALLOWED_ORIGINS` | yes (prod) | `http://localhost:5173` | Frontend origin(s), comma-separated |
| `CSRF_TRUSTED_ORIGINS` | yes (prod) | `http://localhost:5173` | Same as above (used by Django admin) |
| `JWT_ACCESS_MINUTES` | no | `30` | Access-token lifetime |
| `JWT_REFRESH_HOURS` | no | `12` | Refresh-token lifetime (rotated and blacklisted on use) |
| `LOGIN_THROTTLE_RATE` | no | `10/min` | Brute-force protection on the login endpoint |
| `MAX_CASH_RECEIPT` | no | `199999.99` | Largest single cash receipt (Income Tax Act s.269ST bars ₹2,00,000+) |
| `DUPLICATE_WINDOW_MINUTES` | no | `30` | Same loan + same amount within this window needs confirmation |
| `SETTLEMENT_SLA_DAYS` | no | `2` | Deposits not credited after this many days are flagged *delayed* |
| `APP_TIME_ZONE` | no | `Asia/Kolkata` | Business day boundaries for reports and receipt numbers |
| `SEED_DEMO_DATA` | no | `false` | Render build seeds demo data when `true` (only if the DB is empty) |
| `SECURE_SSL_REDIRECT` | no | `1` in prod | Set `0` when TLS terminates elsewhere without forwarding headers |
| `LOG_LEVEL` | no | `INFO` | |

### Frontend (`frontend/.env.example`)

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_URL` | *(empty: same origin)* | Backend base URL in production, e.g. `https://cmrs-api.onrender.com` |
| `VITE_SHOW_DEMO_LOGINS` | `true` | Set `false` to hide the demo-account buttons on the sign-in page |

---

## Deployment

**Backend + database on Render** (free tier):
1. Push this repo to GitHub.
2. Render dashboard → *New* → *Blueprint* → select the repo. `render.yaml` creates the PostgreSQL
   database and the `cmrs-api` web service (build runs migrations and seeds demo data).
3. After the frontend is deployed, set `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` on the service to
   the Vercel URL and redeploy.

**Frontend on Vercel**:
1. *New project* → import the repo → **Root directory: `frontend`** (framework preset: Vite).
2. Environment variable `VITE_API_URL=https://cmrs-api.onrender.com` (your Render URL).
3. Deploy. `vercel.json` rewrites all routes to the SPA.

**If deploying both services through the repo-root Vercel project**:
Set these variables for the backend service in Vercel before redeploying:
`DJANGO_SECRET_KEY` (a unique, generated secret), `DJANGO_DEBUG=0`, and `DATABASE_URL`
pointing to a persistent PostgreSQL database. The backend intentionally refuses to load
without `DJANGO_SECRET_KEY`; SQLite is not suitable for Vercel's serverless runtime.
Set `DJANGO_ALLOWED_HOSTS` to `.vercel.app` (and add any custom domains). If the frontend
calls the backend cross-origin rather than through the `/api` rewrite, also set
`CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` to the frontend origin.

> Render's free web services sleep after inactivity; the first request after a pause takes ~30 s.

---

## Project layout

```
backend/
  config/            settings (env-driven), urls, test settings
  apps/
    core/            Branch, AuditLog, document numbering, money helpers, error envelope, seed command
    accounts/        User (role + branch), JWT auth views, RBAC permissions & row scoping
    lending/         Customer, Loan, Installment; EMI schedule; FIFO allocation
    cash/            Collection (receipt), RepaymentAllocation, CashSubmission (agent → branch)
    banking/         BankDeposit (branch → bank) and settlement (bank → company account)
    reconciliation/  Discrepancy (auto-raised at every stage) + audit-log API
    reports/         Dashboard, branch summary, agent summary
  tests/             pytest suite
frontend/
  src/api/           typed API client (JWT refresh, error envelope), shared types
  src/lib/           paise-based money maths, formatting, hooks
  src/components/    layout, filter bar, modals, UI primitives
  src/pages/         one file per screen
docs/                architecture, API reference, video script
```

Each Django app has `models.py` (data + invariants), `services.py` (business rules, transactions, locks),
`serializers.py` (I/O shape) and `views.py` (HTTP + permissions). Views never change financial state
directly; they call a service.

---

## What I'd improve with more time

- **Digital/UPI collections** via a payment-gateway sandbox (Razorpay test mode): a `UPI` receipt would skip
  agent custody and enter at `DEPOSITED`, settling from the gateway's settlement report through the same
  reconciliation path. The `payment_mode` field and lifecycle already leave room for it.
- **Bank statement import** (CSV/MT940) to auto-match deposits by reference instead of manual entry.
- **Celery + Redis** for scheduled jobs: nightly SLA breach alerts, agents holding cash overnight, auto-escalation.
- **Maker-checker for discrepancy write-offs** above a threshold, and denomination-wise cash counting.
- **Offline-first agent app** (PWA with queued, idempotent submissions — the API already supports it).
- httpOnly-cookie refresh tokens instead of `localStorage`, plus 2FA for Finance and Admin.
- Observability: structured JSON logs, Sentry, and request IDs carried into the audit log.
