import uuid
from decimal import Decimal

import pytest
from django.db import DatabaseError, transaction

from apps.cash import services as cash
from apps.cash.models import Collection
from apps.core.exceptions import ConflictError, DomainError, ForbiddenError, LockedRecordError
from apps.core.models import AuditLog
from apps.lending.models import Installment

pytestmark = pytest.mark.django_db
EMI = Decimal("8884.88")


def collect(api, agent, loan, amount, **extra):
    return api(agent).post("/api/collections/", {"loan": loan.id, "amount": str(amount), **extra}, format="json")


def test_full_emi_payment(api, agent, loan):
    res = collect(api, agent, loan, EMI)
    assert res.status_code == 201
    assert res.data["receipt_number"].startswith("RCP-MUM01-")
    assert res.data["status"] == "COLLECTED"
    first = loan.installments.get(installment_number=1)
    assert first.status == Installment.Status.PAID
    loan.refresh_from_db()
    assert loan.total_paid == EMI
    assert AuditLog.objects.filter(action="collection.recorded").count() == 1


def test_partial_payment_then_spill_over(api, agent, loan):
    assert collect(api, agent, loan, "5000").status_code == 201
    first = loan.installments.get(installment_number=1)
    assert first.status == Installment.Status.PARTIALLY_PAID and first.amount_paid == Decimal("5000.00")

    # 6000 more: 3884.88 closes EMI 1, 2115.12 goes to EMI 2 (oldest first).
    res = collect(api, agent, loan, "6000", confirm_duplicate=True)
    assert res.status_code == 201
    assert [(a["installment_number"], a["amount"]) for a in res.data["allocations"]] == [
        (1, "3884.88"), (2, "2115.12")]
    assert loan.installments.get(installment_number=2).status == Installment.Status.PARTIALLY_PAID


def test_over_collection_rejected(api, agent, loan):
    res = collect(api, agent, loan, loan.total_payable + Decimal("0.01"))
    assert res.status_code == 400
    assert res.data["error"]["code"] == "OVER_COLLECTION"
    assert res.data["error"]["details"]["excess"] == "0.01"
    assert not Collection.objects.exists()


def test_exact_payoff_closes_loan(agent, loan, settings):
    settings.CMRS = {**settings.CMRS, "MAX_CASH_RECEIPT": Decimal("999999")}
    cash.record_collection(agent=agent, loan_id=loan.id, amount=loan.total_payable)
    loan.refresh_from_db()
    assert loan.status == "CLOSED" and loan.outstanding == 0
    with pytest.raises(DomainError) as err:
        cash.record_collection(agent=agent, loan_id=loan.id, amount="1")
    assert err.value.code == "LOAN_CLOSED"


def test_statutory_cash_limit(agent, loan):
    with pytest.raises(DomainError) as err:
        cash.record_collection(agent=agent, loan_id=loan.id, amount="200000")
    assert err.value.code == "CASH_LIMIT_EXCEEDED"


def test_idempotent_retry_returns_same_receipt(api, agent, loan):
    key = str(uuid.uuid4())
    first = collect(api, agent, loan, "1000", idempotency_key=key)
    retry = collect(api, agent, loan, "1000", idempotency_key=key)
    assert first.status_code == 201 and retry.status_code == 200
    assert first.data["receipt_number"] == retry.data["receipt_number"]
    assert Collection.objects.count() == 1


def test_possible_duplicate_needs_confirmation(api, agent, loan):
    collect(api, agent, loan, "1000")
    dup = collect(api, agent, loan, "1000")
    assert dup.status_code == 409 and dup.data["error"]["code"] == "POSSIBLE_DUPLICATE"
    assert collect(api, agent, loan, "1000", confirm_duplicate=True).status_code == 201
    assert Collection.objects.count() == 2


def test_agent_cannot_collect_for_unassigned_customer(api, other_agent, loan):
    res = collect(api, other_agent, loan, "1000")
    assert res.status_code == 403 and res.data["error"]["code"] == "NOT_ASSIGNED"


def test_only_agents_record_collections(api, manager, loan):
    assert collect(api, manager, loan, "1000").status_code == 403


def test_void_reverses_allocation(api, agent, loan):
    res = collect(api, agent, loan, "5000")
    voided = api(agent).post(f"/api/collections/{res.data['id']}/void/", {"reason": "Wrong customer"})
    assert voided.status_code == 200 and voided.data["status"] == "VOIDED"
    loan.refresh_from_db()
    assert loan.total_paid == 0
    assert loan.installments.get(installment_number=1).status == Installment.Status.PENDING


def test_cannot_void_after_handover(agent, loan):
    c, _ = cash.record_collection(agent=agent, loan_id=loan.id, amount="1000")
    cash.submit_cash(agent=agent, collection_ids=[c.id], declared_amount="1000")
    with pytest.raises(LockedRecordError):
        cash.void_collection(c.id, actor=agent, reason="oops")


def test_reconciled_receipt_cannot_be_edited(agent, loan, manager):
    c, _ = cash.record_collection(agent=agent, loan_id=loan.id, amount="1000")
    sub = cash.submit_cash(agent=agent, collection_ids=[c.id], declared_amount="1000")
    cash.approve_submission(sub.id, actor=manager, received_amount="1000")
    c.refresh_from_db()
    c.amount = Decimal("10")
    with pytest.raises(LockedRecordError):
        c.save()
    with pytest.raises(LockedRecordError):
        c.delete()
    # Even a raw UPDATE bypassing the ORM is stopped by the PostgreSQL trigger.
    with pytest.raises(DatabaseError), transaction.atomic():
        Collection.objects.filter(pk=c.pk).update(amount=Decimal("10"))


def test_audit_log_is_append_only(agent, loan):
    cash.record_collection(agent=agent, loan_id=loan.id, amount="1000")
    entry = AuditLog.objects.first()
    with pytest.raises(LockedRecordError):
        entry.save()
    with pytest.raises(DatabaseError), transaction.atomic():
        AuditLog.objects.filter(pk=entry.pk).update(action="tampered")


def test_daily_summary(api, agent, loan):
    collect(api, agent, loan, "1000")
    collect(api, agent, loan, "2500")
    res = api(agent).get("/api/collections/daily-summary/")
    assert res.data["collected_count"] == 2
    assert res.data["collected_amount"] == "3500.00"
    assert res.data["cash_in_hand"] == "3500.00"


def test_agent_sees_only_own_collections(api, agent, other_agent, loan, manager):
    from apps.lending import services
    cust = services.create_customer(actor=manager, full_name="B", phone="9000000001", branch=manager.branch,
                                    assigned_agent=other_agent)
    loan2 = services.create_loan(actor=manager, customer=cust, principal=Decimal("10000"),
                                 annual_interest_rate=Decimal("10"), tenure_months=6,
                                 disbursement_date=loan.disbursement_date)
    cash.record_collection(agent=agent, loan_id=loan.id, amount="100")
    cash.record_collection(agent=other_agent, loan_id=loan2.id, amount="200")
    assert api(agent).get("/api/collections/").data["count"] == 1
    assert api(manager).get("/api/collections/").data["count"] == 2
