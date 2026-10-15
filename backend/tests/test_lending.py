from datetime import date
from decimal import Decimal

import pytest

from apps.lending.models import Installment, Loan
from apps.lending.services import add_months, build_schedule

pytestmark = pytest.mark.django_db


def test_emi_matches_reducing_balance_formula():
    rows = build_schedule(Decimal("100000"), Decimal("12"), 12, date(2026, 1, 31))
    assert rows[0].amount == Decimal("8884.88")
    assert len(rows) == 12
    # Principal components add up to exactly the principal: no paisa lost to rounding.
    assert sum(r.principal for r in rows) == Decimal("100000.00")
    assert all(isinstance(r.amount, Decimal) for r in rows)


def test_zero_interest_schedule():
    rows = build_schedule(Decimal("10000"), Decimal("0"), 3, date(2026, 1, 1))
    assert [r.amount for r in rows] == [Decimal("3333.33"), Decimal("3333.33"), Decimal("3333.34")]


def test_due_dates_clamp_to_month_end():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)


def test_loan_creation_builds_schedule(loan):
    assert loan.installments.count() == 12
    assert loan.total_payable == sum(i.amount_due for i in loan.installments.all())
    assert loan.outstanding == loan.total_payable
    assert loan.loan_number.startswith("LN-MUM01-")


def test_outstanding_and_history_endpoints(api, manager, loan):
    client = api(manager)
    res = client.get(f"/api/loans/{loan.id}/")
    assert res.status_code == 200
    assert res.data["outstanding"] == str(loan.total_payable)
    assert Decimal(res.data["overdue_amount"]) == loan.installments.first().amount_due  # first EMI is past due
    assert len(client.get(f"/api/loans/{loan.id}/schedule/").data) == 12
    assert client.get(f"/api/loans/{loan.id}/repayments/").data == []


def test_db_rejects_paid_above_payable(loan):
    from django.db import IntegrityError, transaction
    with pytest.raises(IntegrityError), transaction.atomic():
        Loan.objects.filter(pk=loan.pk).update(total_paid=loan.total_payable + 1)
    inst = loan.installments.first()
    with pytest.raises(IntegrityError), transaction.atomic():
        Installment.objects.filter(pk=inst.pk).update(amount_paid=inst.amount_due + 1)


def test_manager_cannot_create_customer_in_other_branch(api, manager, other_branch):
    res = api(manager).post("/api/customers/", {"full_name": "X", "phone": "9876500000", "branch": other_branch.id})
    assert res.status_code == 403


def test_agent_cannot_create_customer(api, agent):
    res = api(agent).post("/api/customers/", {"full_name": "X", "phone": "9876500000"})
    assert res.status_code == 403


def test_agent_sees_only_assigned_customers(api, agent, other_agent, customer, manager):
    from apps.lending import services
    services.create_customer(actor=manager, full_name="Other", phone="9000000000", branch=manager.branch,
                             assigned_agent=other_agent)
    res = api(agent).get("/api/customers/")
    assert [c["id"] for c in res.data["results"]] == [customer.id]
