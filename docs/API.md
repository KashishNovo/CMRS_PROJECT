# API reference

Interactive documentation (generated from the code, always current):

* Swagger UI — `/api/docs/`
* ReDoc — `/api/redoc/`
* OpenAPI 3 schema — `/api/schema/`

## Conventions

* **Auth**: `POST /api/auth/login/` → `{access, refresh, user}`. Send `Authorization: Bearer <access>`.
  Refresh with `POST /api/auth/refresh/ {refresh}` (refresh tokens rotate; old ones are blacklisted).
* **Money**: decimal strings with two places, e.g. `"48500.00"`. Send amounts as strings too.
* **Lists** are paginated: `?page=2&page_size=50` → `{count, next, previous, results}`.
  Most lists support `?search=` and `?ordering=`.
* **Common filters**: `date_from`, `date_to` (YYYY-MM-DD, inclusive), `branch`, `agent`, `status`.
  Filters only narrow results; rows are always scoped to the caller's role first.
* **Errors** always look like:
  ```json
  {"error": {"code": "OVER_COLLECTION", "message": "Amount ₹12000.00 exceeds the outstanding balance of ₹8884.88.",
             "details": {"outstanding": "8884.88", "excess": "3115.12"}}}
  ```
  `400` validation/business rule · `401` not signed in · `403` role not allowed · `404` not found or
  outside your scope · `409` conflict with current state (duplicate, already reviewed, locked).

## Endpoints

| Method & path | Roles | Description |
|---|---|---|
| `POST /api/auth/login/` | public (10/min) | JWT pair + profile |
| `POST /api/auth/refresh/` | public | New access token |
| `POST /api/auth/logout/` | any | Blacklist refresh token |
| `GET /api/auth/me/` | any | Current user |
| `GET/POST/PATCH /api/users/` | admin (managers: list own branch) | Staff accounts |
| `GET/POST/PATCH /api/branches/` | read: any · write: admin | Branches |
| `GET/POST/PATCH /api/customers/` | read: scoped · write: admin, manager | Customers, with `outstanding` and `active_loans` |
| `GET /api/loans/` · `POST /api/loans/` | read: scoped · create: admin, manager | Loans; create generates the EMI schedule |
| `POST /api/loans/preview-schedule/` | admin, manager | EMI and schedule without saving |
| `GET /api/loans/{id}/schedule/` | scoped | Instalments with paid/balance/overdue |
| `GET /api/loans/{id}/repayments/` | scoped | Repayment history |
| `GET /api/collections/` | scoped | Receipts; filters `status` (multi), `agent`, `branch`, `loan`, dates |
| `POST /api/collections/` | agent | Record repayment `{loan, amount, idempotency_key?, remarks?, confirm_duplicate?}` → 201 (new) / 200 (idempotent replay) |
| `POST /api/collections/{id}/void/` | agent (own), manager, admin | `{reason}`; only while `COLLECTED` |
| `GET /api/collections/daily-summary/?date=` | scoped | Day's total, cash in hand, pending verification |
| `GET /api/submissions/` | scoped | Agent hand-overs |
| `POST /api/submissions/` | agent | `{collection_ids, declared_amount, notes?}` |
| `POST /api/submissions/{id}/approve/` | manager, admin | `{received_amount, notes}` (notes required if different) |
| `POST /api/submissions/{id}/reject/` | manager, admin | `{reason}` |
| `GET /api/deposits/` | manager (branch), finance, admin | Filters `status`, `branch`, dates, `delayed=true` |
| `GET /api/deposits/available-submissions/` | manager | Approved cash not yet banked |
| `POST /api/deposits/` | manager | `{submission_ids, bank_name, account_number?, reference_number, deposit_date, amount, mismatch_reason?}` |
| `POST /api/deposits/{id}/settle/` | finance, admin | `{settled_amount, settlement_date, settlement_reference?, notes}` |
| `POST /api/deposits/{id}/fail/` | finance, admin | `{reason}` |
| `GET /api/discrepancies/` | scoped | Filters `stage`, `status`, `direction`, `branch`, `agent`, dates |
| `POST /api/discrepancies/{id}/resolve/` | manager (own branch, not bank stage), finance, admin | `{resolution, notes}` |
| `GET /api/audit-logs/` | manager (branch), finance, admin | Filters `entity_type`, `entity_id`, `action`, `actor`, dates |
| `GET /api/reports/dashboard/` | scoped | Flow (period), position (now), lifecycle, trend, discrepancies |
| `GET /api/reports/branches/` | scoped | Per-branch summary |
| `GET /api/reports/agents/` | scoped | Per-agent summary |
| `GET /api/health/` | public | Liveness + DB check |

## Error codes

| Code | HTTP | Meaning |
|---|---|---|
| `VALIDATION_ERROR` | 400 | Field errors in `details` |
| `INVALID_AMOUNT` | 400 | Zero/negative amount |
| `OVER_COLLECTION` | 400 | Receipt exceeds loan outstanding |
| `CASH_LIMIT_EXCEEDED` | 400 | Above `MAX_CASH_RECEIPT` |
| `LOAN_CLOSED` | 400 | Loan already repaid |
| `NOT_ASSIGNED` | 403 | Agent collecting from a customer not assigned to them |
| `POSSIBLE_DUPLICATE` | 409 | Same loan + amount recently; resend with `confirm_duplicate: true` |
| `IDEMPOTENCY_KEY_REUSED` | 409 | Key used by another agent |
| `RECEIPT_NOT_AVAILABLE` | 409 | Receipt already handed over / voided |
| `NOTES_REQUIRED` / `REASON_REQUIRED` | 400 | Explanation needed for a difference / rejection |
| `ALREADY_REVIEWED` / `ALREADY_SETTLED` / `ALREADY_RESOLVED` | 409 | State already final |
| `SUBMISSION_NOT_AVAILABLE` | 409 | Not approved, other branch, or already in a live deposit |
| `DEPOSIT_MISMATCH` | 400 | Slip differs from verified cash; give `mismatch_reason` |
| `DUPLICATE_BANK_REFERENCE` | 409 | Reference already recorded at that bank |
| `INVALID_DATE` | 400 | Future date, or settlement before deposit |
| `RECORD_LOCKED` | 409 | Attempt to change a reconciled record |
| `FORBIDDEN` | 403 | Role or branch not allowed |
| `CONSTRAINT_VIOLATION` | 409 | A database constraint caught a conflicting change |

## Example: full lifecycle with curl

```bash
API=http://localhost:8000/api
tok() { curl -s $API/auth/login/ -H 'Content-Type: application/json' -d "{\"username\":\"$1\",\"password\":\"Cmrs@2026\"}" | jq -r .access; }
AGENT=$(tok agent.ravi); MGR=$(tok manager.mum); FIN=$(tok finance)

# agent: pick a loan and collect (re-running within 30 min trips the duplicate guard: 409 POSSIBLE_DUPLICATE)
LOAN=$(curl -s "$API/loans/?status=ACTIVE" -H "Authorization: Bearer $AGENT" | jq '.results[0].id')
RCP=$(curl -s $API/collections/ -H "Authorization: Bearer $AGENT" -H 'Content-Type: application/json' \
  -d "{\"loan\":$LOAN,\"amount\":\"750.00\",\"idempotency_key\":\"$(uuidgen)\"}" | jq .id)

# agent: hand over
SUB=$(curl -s $API/submissions/ -H "Authorization: Bearer $AGENT" -H 'Content-Type: application/json' \
  -d "{\"collection_ids\":[$RCP],\"declared_amount\":\"750.00\"}" | jq .id)

# manager: counted 700 -> shortage of 50 recorded against the agent
curl -s $API/submissions/$SUB/approve/ -H "Authorization: Bearer $MGR" -H 'Content-Type: application/json' \
  -d '{"received_amount":"700.00","notes":"Short by 50"}' | jq '{status,difference}'

# manager: bank it
DEP=$(curl -s $API/deposits/ -H "Authorization: Bearer $MGR" -H 'Content-Type: application/json' \
  -d "{\"submission_ids\":[$SUB],\"bank_name\":\"HDFC Bank\",\"reference_number\":\"DEMO-$RANDOM\",\"deposit_date\":\"$(date +%F)\",\"amount\":\"700.00\"}" | jq .id)

# finance: confirm the credit
curl -s $API/deposits/$DEP/settle/ -H "Authorization: Bearer $FIN" -H 'Content-Type: application/json' \
  -d "{\"settled_amount\":\"700.00\",\"settlement_date\":\"$(date +%F)\"}" | jq '{status}'
```
