"""Customer and loan business logic: schedule generation and repayment allocation."""
import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import transaction

from apps.core import audit
from apps.core.exceptions import DomainError
from apps.core.models import next_document_number
from apps.core.money import ZERO, quantize, to_money

from .models import Customer, Installment, Loan


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year, month = d.year + month_index // 12, month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


@dataclass
class ScheduleRow:
    number: int
    due_date: date
    principal: Decimal
    interest: Decimal
    amount: Decimal


def build_schedule(principal: Decimal, annual_rate: Decimal, months: int, disbursed: date) -> list[ScheduleRow]:
    """
    Reducing-balance EMI schedule, all in Decimal.

    EMI = P·r·(1+r)^n / ((1+r)^n − 1), rounded to the paisa. Rounding drift is absorbed
    by the final instalment so the principal components always sum to exactly P.
    """
    principal, annual_rate = to_money(principal), Decimal(annual_rate)
    r = annual_rate / Decimal(1200)
    if r == 0:
        emi = quantize(principal / months)
    else:
        growth = (1 + r) ** months
        emi = quantize(principal * r * growth / (growth - 1))

    rows, balance = [], principal
    for n in range(1, months + 1):
        interest = quantize(balance * r)
        if n == months:
            principal_part = balance
        else:
            principal_part = min(emi - interest, balance)
        balance -= principal_part
        rows.append(ScheduleRow(n, add_months(disbursed, n), principal_part, interest, principal_part + interest))
    return rows


@transaction.atomic
def create_customer(*, actor, **data) -> Customer:
    branch = data["branch"]
    agent = data.get("assigned_agent")
    if agent and (not agent.is_agent or agent.branch_id != branch.id):
        raise DomainError("The assigned agent must be a collection agent of the same branch.", "INVALID_AGENT")
    customer = Customer.objects.create(
        customer_code=next_document_number("CUS", branch.code, daily=False), created_by=actor, **data
    )
    audit.record(actor, "customer.created", customer, ref=customer.customer_code, name=customer.full_name)
    return customer


@transaction.atomic
def update_customer(customer: Customer, *, actor, **data) -> Customer:
    branch = data.get("branch", customer.branch)
    agent = data.get("assigned_agent", customer.assigned_agent)
    if branch.id != customer.branch_id and customer.loans.filter(status=Loan.Status.ACTIVE).exists():
        raise DomainError("A customer with an active loan cannot be moved to another branch.", "BRANCH_CHANGE_BLOCKED")
    if agent and (not agent.is_agent or agent.branch_id != branch.id):
        raise DomainError("The assigned agent must be a collection agent of the same branch.", "INVALID_AGENT")
    before = {k: str(getattr(customer, k)) for k in data}
    for key, value in data.items():
        setattr(customer, key, value)
    customer.save()
    audit.record(actor, "customer.updated", customer, ref=customer.customer_code, before=before,
                 after={k: str(v) for k, v in data.items()})
    return customer


@transaction.atomic
def create_loan(*, actor, customer: Customer, principal, annual_interest_rate, tenure_months, disbursement_date) -> Loan:
    if not customer.is_active:
        raise DomainError("Cannot issue a loan to an inactive customer.", "CUSTOMER_INACTIVE")
    rows = build_schedule(principal, annual_interest_rate, tenure_months, disbursement_date)
    loan = Loan.objects.create(
        loan_number=next_document_number("LN", customer.branch.code, daily=False),
        customer=customer,
        branch=customer.branch,
        principal=to_money(principal),
        annual_interest_rate=annual_interest_rate,
        tenure_months=tenure_months,
        disbursement_date=disbursement_date,
        emi_amount=rows[0].amount,
        total_payable=sum((row.amount for row in rows), ZERO),
        created_by=actor,
    )
    Installment.objects.bulk_create(
        Installment(
            loan=loan,
            installment_number=row.number,
            due_date=row.due_date,
            principal_component=row.principal,
            interest_component=row.interest,
            amount_due=row.amount,
        )
        for row in rows
    )
    audit.record(actor, "loan.created", loan, ref=loan.loan_number, principal=loan.principal,
                 total_payable=loan.total_payable, tenure_months=tenure_months)
    return loan


def apply_payment(loan: Loan, amount: Decimal) -> list[tuple[Installment, Decimal]]:
    """
    Allocate `amount` to the oldest unpaid instalments first (FIFO). Caller must hold a
    row lock on `loan`. Returns (installment, allocated) pairs for the allocation ledger.
    """
    remaining = amount
    allocations = []
    installments = (
        loan.installments.select_for_update().exclude(status=Installment.Status.PAID).order_by("installment_number")
    )
    for inst in installments:
        if remaining <= 0:
            break
        take = min(inst.balance, remaining)
        inst.amount_paid += take
        inst.refresh_status()
        inst.save(update_fields=["amount_paid", "status"])
        allocations.append((inst, take))
        remaining -= take
    if remaining > 0:  # guarded earlier; defensive
        raise DomainError("Payment exceeds the outstanding balance.", "OVER_COLLECTION")
    loan.total_paid += amount
    loan.status = Loan.Status.CLOSED if loan.total_paid >= loan.total_payable else Loan.Status.ACTIVE
    loan.save(update_fields=["total_paid", "status", "updated_at"])
    return allocations


def reverse_payment(loan: Loan, allocations) -> None:
    """Undo allocations (used when an un-submitted receipt is voided). Caller locks `loan`."""
    total = ZERO
    for alloc in allocations:
        inst = Installment.objects.select_for_update().get(pk=alloc.installment_id)
        inst.amount_paid -= alloc.amount
        inst.refresh_status()
        inst.save(update_fields=["amount_paid", "status"])
        total += alloc.amount
    loan.total_paid -= total
    loan.status = Loan.Status.ACTIVE
    loan.save(update_fields=["total_paid", "status", "updated_at"])
