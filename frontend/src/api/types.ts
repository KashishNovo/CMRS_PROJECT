/** Money is always a decimal string from the API ("1500.00"). Never parse it into a float for arithmetic. */
export type Money = string

export type Role = 'ADMIN' | 'FINANCE' | 'BRANCH_MANAGER' | 'AGENT'

export interface Branch {
  id: number
  code: string
  name: string
  city: string
  address: string
  is_active: boolean
}

export interface User {
  id: number
  username: string
  first_name: string
  last_name: string
  full_name: string
  email: string
  phone: string
  role: Role
  role_display: string
  branch: number | null
  branch_detail: Branch | null
  is_active: boolean
  last_login: string | null
}

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface Customer {
  id: number
  customer_code: string
  full_name: string
  phone: string
  email: string
  address: string
  id_number: string
  branch: number
  branch_code: string
  assigned_agent: number | null
  assigned_agent_name: string | null
  is_active: boolean
  outstanding: Money
  active_loans: number
  created_at: string
}

export interface Loan {
  id: number
  loan_number: string
  customer: number
  customer_name: string
  customer_code: string
  branch: number
  branch_code: string
  principal: Money
  annual_interest_rate: string
  tenure_months: number
  disbursement_date: string
  emi_amount: Money
  total_payable: Money
  total_paid: Money
  outstanding: Money
  overdue_amount: Money
  next_due_date: string | null
  next_due_amount: Money | null
  status: 'ACTIVE' | 'CLOSED'
  created_at: string
}

export interface Installment {
  id?: number
  installment_number: number
  due_date: string
  principal_component: Money
  interest_component: Money
  amount_due: Money
  amount_paid?: Money
  balance?: Money
  status?: 'PENDING' | 'PARTIALLY_PAID' | 'PAID'
  is_overdue?: boolean
}

export type CollectionStatus = 'COLLECTED' | 'SUBMITTED' | 'BRANCH_RECEIVED' | 'DEPOSITED' | 'SETTLED' | 'VOIDED'

export interface Collection {
  id: number
  receipt_number: string
  loan: number
  loan_number: string
  customer: number
  customer_name: string
  customer_code: string
  agent: number
  agent_name: string
  branch: number
  branch_code: string
  amount: Money
  payment_mode: string
  collected_at: string
  status: CollectionStatus
  status_display: string
  remarks: string
  void_reason: string
  voided_at: string | null
  allocations: { installment_number: number; due_date: string; amount: Money }[]
  loan_outstanding: Money
}

export interface Submission {
  id: number
  submission_number: string
  agent: number
  agent_name: string
  branch: number
  branch_code: string
  expected_amount: Money
  declared_amount: Money
  received_amount: Money | null
  difference: Money | null
  status: 'PENDING' | 'APPROVED' | 'REJECTED'
  agent_notes: string
  reviewed_by_name: string | null
  reviewed_at: string | null
  review_notes: string
  created_at: string
  receipt_count: number | null
  collections?: Collection[]
  deposit_numbers: string[]
}

export type DepositStatus = 'PENDING_SETTLEMENT' | 'SETTLED' | 'SETTLEMENT_MISMATCH' | 'FAILED'

export interface Deposit {
  id: number
  deposit_number: string
  branch: number
  branch_code: string
  bank_name: string
  account_number: string
  reference_number: string
  deposit_date: string
  reconciled_amount: Money
  amount: Money
  deposit_difference: Money
  mismatch_reason: string
  status: DepositStatus
  status_display: string
  is_delayed: boolean
  created_by_name: string | null
  created_at: string
  settled_amount: Money | null
  settlement_date: string | null
  settlement_reference: string
  settlement_difference: Money | null
  settlement_notes: string
  settled_by_name: string | null
  settled_at: string | null
  failure_reason: string
  submissions?: Submission[]
}

export interface Discrepancy {
  id: number
  stage: 'SUBMISSION' | 'DEPOSIT' | 'SETTLEMENT'
  stage_display: string
  direction: 'SHORTAGE' | 'EXCESS'
  status: 'OPEN' | 'RESOLVED'
  branch: number
  branch_code: string
  agent: number | null
  agent_name: string | null
  submission: number | null
  submission_number: string | null
  deposit: number | null
  deposit_number: string | null
  expected_amount: Money
  actual_amount: Money
  amount: Money
  reason: string
  raised_by_name: string | null
  created_at: string
  resolution: string
  resolution_notes: string
  resolved_by_name: string | null
  resolved_at: string | null
}

export interface AuditEntry {
  id: number
  created_at: string
  actor_name: string
  action: string
  entity_type: string
  entity_id: string
  entity_ref: string
  branch_code: string | null
  changes: Record<string, unknown>
  ip_address: string | null
}

export interface Dashboard {
  filters: { date_from: string; date_to: string; branch: string | null; agent: string | null; status: string | null }
  flow: {
    expected: Money
    expected_paid: Money
    collection_efficiency: string | null
    collected: Money
    collected_count: number
    received_at_branch: Money
    deposited: Money
    settled: Money
  }
  position: {
    cash_with_agents: Money
    pending_verification: Money
    cash_at_branch: Money
    in_transit_to_bank: Money
    delayed_deposits: number
    delayed_amount: Money
    outstanding: Money
    active_loans: number
  }
  discrepancies: {
    open_count: number
    open_shortage: Money
    open_excess: Money
    by_stage: { stage: string; count: number; amount: Money }[]
  }
  lifecycle: { stage: CollectionStatus; label: string; amount: Money; at_stage: Money }[]
  trend: { date: string; collected: Money; receipts: number; expected: Money }[]
}

export interface BranchSummaryRow {
  branch: number
  code: string
  name: string
  collected: Money
  receipts: number
  cash_with_agents: Money
  pending_verification: Money
  cash_at_branch: Money
  deposited: Money
  settled: Money
  open_discrepancies: number
  open_discrepancy_amount: Money
}

export interface AgentSummaryRow {
  agent: number
  name: string
  branch_code: string | null
  assigned_customers: number
  expected: Money
  collected: Money
  receipts: number
  cash_in_hand: Money
  pending_verification: Money
  open_shortage: Money
  rejected_submissions: number
}

export interface DailySummary {
  date: string
  collected_count: number
  collected_amount: Money
  cash_in_hand: Money
  cash_in_hand_receipts: number
  pending_verification: Money
}
