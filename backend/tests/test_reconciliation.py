from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.banking import services as banking
from apps.banking.models import BankDeposit
from apps.cash import services as cash
from apps.cash.models import CashSubmission, Collection
from apps.core.exceptions import ConflictError, DomainError, ForbiddenError
from apps.reconciliation.models import Discrepancy

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate


@pytest.fixture
def receipts(agent, loan, settings):
    """Three receipts totalling ₹50,000 (the problem statement's example)."""
    settings.CMRS = {**settings.CMRS, "DUPLICATE_WINDOW_MINUTES": 0}
    return [cash.record_collection(agent=agent, loan_id=loan.id, amount=a)[0] for a in ("20000", "20000", "10000")]


@pytest.fixture
def submission(agent, receipts):
    return cash.submit_cash(agent=agent, collection_ids=[r.id for r in receipts], declared_amount="50000")


def approved(manager, submission, amount="50000", notes=""):
    return cash.approve_submission(submission.id, actor=manager, received_amount=amount, notes=notes)


# ---------------------------------------------------------------- agent -> branch
def test_submission_totals_receipts(submission, receipts):
    assert submission.expected_amount == Decimal("50000.00")
    assert set(Collection.objects.values_list("status", flat=True)) == {"SUBMITTED"}


def test_receipt_cannot_be_submitted_twice(agent, receipts, submission):
    with pytest.raises(ConflictError) as err:
        cash.submit_cash(agent=agent, collection_ids=[receipts[0].id], declared_amount="20000")
    assert err.value.code == "RECEIPT_NOT_AVAILABLE"


def test_exact_count_approves_without_discrepancy(manager, submission):
    sub = approved(manager, submission)
    assert sub.status == "APPROVED" and sub.difference == 0
    assert not Discrepancy.objects.exists()
    assert set(Collection.objects.values_list("status", flat=True)) == {"BRANCH_RECEIVED"}


def test_shortage_records_discrepancy_against_agent(api, manager, submission, agent):
    client = api(manager)
    no_notes = client.post(f"/api/submissions/{submission.id}/approve/", {"received_amount": "48500"})
    assert no_notes.status_code == 400 and no_notes.data["error"]["code"] == "NOTES_REQUIRED"

    res = client.post(f"/api/submissions/{submission.id}/approve/",
                      {"received_amount": "48500", "notes": "Short by 1500"})
    assert res.status_code == 200
    assert (res.data["expected_amount"], res.data["received_amount"], res.data["difference"]) == (
        "50000.00", "48500.00", "1500.00")
    d = Discrepancy.objects.get()
    assert (d.stage, d.direction, d.amount, d.agent) == ("SUBMISSION", "SHORTAGE", Decimal("1500.00"), agent)


def test_excess_cash_is_recorded(manager, submission):
    approved(manager, submission, "50200", "Extra 200")
    assert Discrepancy.objects.get().direction == Discrepancy.Direction.EXCESS


def test_submission_cannot_be_reviewed_twice(manager, submission):
    approved(manager, submission)
    with pytest.raises(ConflictError):
        approved(manager, submission)
    with pytest.raises(ConflictError):
        cash.reject_submission(submission.id, actor=manager, reason="late")


def test_rejection_returns_cash_to_agent_and_allows_resubmission(api, manager, agent, submission, receipts):
    res = api(manager).post(f"/api/submissions/{submission.id}/reject/", {"reason": "Counterfeit note"})
    assert res.status_code == 200 and res.data["status"] == "REJECTED"
    assert set(Collection.objects.values_list("status", flat=True)) == {"COLLECTED"}
    again = cash.submit_cash(agent=agent, collection_ids=[r.id for r in receipts], declared_amount="50000")
    assert again.status == "PENDING"
    assert receipts[0].submissions.count() == 2  # history of both hand-overs kept


def test_manager_of_other_branch_cannot_review(api, other_manager, submission):
    assert api(other_manager).post(f"/api/submissions/{submission.id}/approve/",
                                   {"received_amount": "50000"}).status_code == 404  # not even visible
    with pytest.raises(ForbiddenError):
        cash.approve_submission(submission.id, actor=other_manager, received_amount="50000")


def test_agent_cannot_approve(api, agent, submission):
    assert api(agent).post(f"/api/submissions/{submission.id}/approve/",
                           {"received_amount": "50000"}).status_code == 403


# ---------------------------------------------------------------- branch -> bank
def deposit(manager, subs, amount="50000", ref="CHQ001", reason="", bank="HDFC Bank"):
    return banking.create_deposit(actor=manager, submission_ids=[s.id for s in subs], bank_name=bank,
                                  account_number="5020", reference_number=ref, deposit_date=TODAY(),
                                  amount=amount, mismatch_reason=reason)


def test_deposit_moves_receipts_to_deposited(api, manager, submission):
    approved(manager, submission)
    avail = api(manager).get("/api/deposits/available-submissions/").data
    assert [s["id"] for s in avail] == [submission.id]
    res = api(manager).post("/api/deposits/", {
        "submission_ids": [submission.id], "bank_name": "HDFC Bank", "reference_number": "CHQ001",
        "deposit_date": str(TODAY()), "amount": "50000"}, format="json")
    assert res.status_code == 201 and res.data["status"] == "PENDING_SETTLEMENT"
    assert set(Collection.objects.values_list("status", flat=True)) == {"DEPOSITED"}
    assert api(manager).get("/api/deposits/available-submissions/").data == []


def test_deposit_against_branch_reconciled_amount_not_receipts(manager, submission):
    """After a shortage, the branch can only deposit what it actually counted."""
    approved(manager, submission, "48500", "short")
    dep = deposit(manager, [submission], amount="48500")
    assert dep.reconciled_amount == Decimal("48500.00") and dep.deposit_difference == 0


def test_deposit_mismatch_needs_reason_and_raises_discrepancy(manager, submission):
    approved(manager, submission)
    with pytest.raises(DomainError) as err:
        deposit(manager, [submission], amount="49500")
    assert err.value.code == "DEPOSIT_MISMATCH"
    dep = deposit(manager, [submission], amount="49500", reason="Soiled note returned by teller")
    d = Discrepancy.objects.get()
    assert (d.stage, d.deposit, d.direction, d.amount) == ("DEPOSIT", dep, "SHORTAGE", Decimal("500.00"))


def test_duplicate_bank_reference_rejected_case_insensitive(manager, agent, loan, submission):
    approved(manager, submission)
    deposit(manager, [submission], ref="ABC123")
    c, _ = cash.record_collection(agent=agent, loan_id=loan.id, amount="777")
    sub2 = cash.submit_cash(agent=agent, collection_ids=[c.id], declared_amount="777")
    approved(manager, sub2, "777")
    with pytest.raises(ConflictError) as err:
        deposit(manager, [sub2], amount="777", ref=" abc123 ", bank="hdfc bank")
    assert err.value.code == "DUPLICATE_BANK_REFERENCE"


def test_submission_cannot_be_deposited_twice(manager, submission):
    approved(manager, submission)
    deposit(manager, [submission])
    with pytest.raises(ConflictError) as err:
        deposit(manager, [submission], ref="OTHER")
    assert err.value.code == "SUBMISSION_NOT_AVAILABLE"


def test_pending_submission_cannot_be_deposited(manager, submission):
    with pytest.raises(ConflictError):
        deposit(manager, [submission])


def test_future_deposit_date_rejected(manager, submission):
    approved(manager, submission)
    with pytest.raises(DomainError):
        banking.create_deposit(actor=manager, submission_ids=[submission.id], bank_name="HDFC",
                               account_number="", reference_number="X", amount="50000",
                               deposit_date=TODAY() + timedelta(days=1))


# ---------------------------------------------------------------- bank -> company account
@pytest.fixture
def pending_deposit(manager, submission):
    approved(manager, submission)
    return deposit(manager, [submission])


def test_settlement_exact(api, finance, pending_deposit):
    res = api(finance).post(f"/api/deposits/{pending_deposit.id}/settle/",
                            {"settled_amount": "50000", "settlement_date": str(TODAY())})
    assert res.status_code == 200 and res.data["status"] == "SETTLED"
    assert set(Collection.objects.values_list("status", flat=True)) == {"SETTLED"}


def test_settlement_mismatch(finance, pending_deposit):
    with pytest.raises(DomainError):
        banking.settle_deposit(pending_deposit.id, actor=finance, settled_amount="49900", settlement_date=TODAY())
    dep = banking.settle_deposit(pending_deposit.id, actor=finance, settled_amount="49900", settlement_date=TODAY(),
                                 notes="Bank charges")
    assert dep.status == "SETTLEMENT_MISMATCH" and dep.settlement_difference == Decimal("100.00")
    d = Discrepancy.objects.get()
    assert (d.stage, d.direction, d.amount) == ("SETTLEMENT", "SHORTAGE", Decimal("100.00"))


def test_settled_deposit_is_frozen(finance, pending_deposit):
    dep = banking.settle_deposit(pending_deposit.id, actor=finance, settled_amount="50000", settlement_date=TODAY())
    with pytest.raises(ConflictError):
        banking.settle_deposit(dep.id, actor=finance, settled_amount="1", settlement_date=TODAY())
    from django.db import DatabaseError, transaction
    with pytest.raises(DatabaseError), transaction.atomic():
        BankDeposit.objects.filter(pk=dep.pk).update(settled_amount=Decimal("1"))


def test_manager_cannot_settle(api, manager, pending_deposit):
    assert api(manager).post(f"/api/deposits/{pending_deposit.id}/settle/",
                             {"settled_amount": "50000", "settlement_date": str(TODAY())}).status_code == 403


def test_failed_deposit_releases_cash_for_redeposit(manager, finance, submission, pending_deposit):
    banking.fail_deposit(pending_deposit.id, actor=finance, reason="Slip returned")
    assert set(Collection.objects.values_list("status", flat=True)) == {"BRANCH_RECEIVED"}
    again = deposit(manager, [submission], ref="CHQ002")
    assert again.status == "PENDING_SETTLEMENT"
    assert submission.deposits.count() == 2


def test_delayed_settlement_flag(api, finance, manager, submission):
    approved(manager, submission)
    old = banking.create_deposit(actor=manager, submission_ids=[submission.id], bank_name="HDFC", account_number="",
                                 reference_number="OLD1", amount="50000", deposit_date=TODAY() - timedelta(days=5))
    res = api(finance).get("/api/deposits/?delayed=true")
    assert [d["id"] for d in res.data["results"]] == [old.id]
    assert res.data["results"][0]["is_delayed"] is True


def test_agent_cannot_see_deposits(api, agent, pending_deposit):
    assert api(agent).get("/api/deposits/").data["count"] == 0


# ---------------------------------------------------------------- discrepancies & dashboard
def test_resolve_discrepancy(api, manager, submission):
    approved(manager, submission, "48500", "short")
    d = Discrepancy.objects.get()
    res = api(manager).post(f"/api/discrepancies/{d.id}/resolve/",
                            {"resolution": "RECOVERED", "notes": "Deducted from salary"})
    assert res.status_code == 200 and res.data["status"] == "RESOLVED"
    again = api(manager).post(f"/api/discrepancies/{d.id}/resolve/", {"resolution": "OTHER", "notes": "x"})
    assert again.status_code == 409


def test_dashboard_tracks_whole_lifecycle(api, admin, finance, manager, agent, loan, submission):
    approved(manager, submission, "48500", "short")
    dep = deposit(manager, [submission], amount="48500")
    banking.settle_deposit(dep.id, actor=finance, settled_amount="48500", settlement_date=TODAY())
    cash.record_collection(agent=agent, loan_id=loan.id, amount="300")  # still with agent

    data = api(admin).get("/api/reports/dashboard/").data
    assert data["flow"]["collected"] == "50300.00"
    assert data["flow"]["received_at_branch"] == "48500.00"
    assert data["flow"]["deposited"] == "48500.00"
    assert data["flow"]["settled"] == "48500.00"
    assert data["position"]["cash_with_agents"] == "300.00"
    assert data["discrepancies"]["open_shortage"] == "1500.00"
    stages = {s["stage"]: s["amount"] for s in data["lifecycle"]}
    assert stages["COLLECTED"] == "50300.00" and stages["SETTLED"] == "50000.00"

    # Branch filter narrows; managers can't widen beyond their branch.
    other = api(admin).get("/api/reports/dashboard/?branch=999999").data
    assert other["flow"]["collected"] == "0.00"
    agent_view = api(agent).get("/api/reports/dashboard/").data
    assert agent_view["flow"]["deposited"] == "0.00"


def test_branch_and_agent_summaries(api, admin, manager, submission):
    approved(manager, submission)
    branches = api(admin).get("/api/reports/branches/").data["results"]
    assert branches[0]["cash_at_branch"] == "50000.00"
    agents = api(manager).get("/api/reports/agents/").data["results"]
    assert agents[0]["collected"] == "50000.00"
