"""
Agent-side cash workflow: recording receipts and handing cash to the branch,
plus the branch manager's verification of each hand-over.

Every function here runs in a transaction and takes row locks on the records it
changes, so concurrent requests (double taps, two managers on one submission)
cannot produce double counting.
"""
import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core import audit
from apps.core.exceptions import ConflictError, DomainError, ForbiddenError, LockedRecordError
from apps.core.models import next_document_number
from apps.core.money import ZERO, to_money
from apps.lending.models import Loan
from apps.lending.services import apply_payment, reverse_payment
from apps.reconciliation.models import Discrepancy
from apps.reconciliation.services import raise_discrepancy

from .models import CashSubmission, Collection, RepaymentAllocation


# --------------------------------------------------------------------------- receipts
@transaction.atomic
def record_collection(*, agent, loan_id: int, amount, idempotency_key: uuid.UUID | None = None,
                      remarks: str = "", confirm_duplicate: bool = False,
                      collected_at=None) -> tuple[Collection, bool]:
    """
    Record a cash repayment collected by `agent`. Returns (collection, created).

    Rules:
    * Only collection agents, only for customers assigned to them.
    * Amount > 0, <= loan outstanding (no over-collection), <= statutory cash limit.
    * Same idempotency key -> the original receipt is returned (safe retries).
    * Same loan + same amount inside the duplicate window -> rejected unless confirm_duplicate.
    * Customer liability is discharged at collection: the payment is allocated to
      instalments immediately (the receipt is the customer's proof of payment).

    `collected_at` is not exposed through the API (the server clock is authoritative);
    it exists for data migration / demo seeding only.
    """
    if not agent.is_agent:
        raise ForbiddenError("Only collection agents can record cash collections.")

    if idempotency_key:
        existing = Collection.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            if existing.agent_id != agent.id:
                raise ConflictError("This request key was already used.", "IDEMPOTENCY_KEY_REUSED")
            return existing, False

    amount = to_money(amount)
    if amount <= 0:
        raise DomainError("Amount must be greater than zero.", "INVALID_AMOUNT")
    limit = settings.CMRS["MAX_CASH_RECEIPT"]
    if amount > limit:
        raise DomainError(
            f"Cash receipts above ₹{limit} are not permitted (Income Tax Act s.269ST). Collect digitally instead.",
            "CASH_LIMIT_EXCEEDED", {"limit": str(limit)},
        )

    try:
        loan = Loan.objects.select_for_update(of=("self",)).select_related("customer", "branch").get(pk=loan_id)
    except Loan.DoesNotExist:
        raise DomainError("Loan not found.", "LOAN_NOT_FOUND", status_code=404)
    if loan.customer.assigned_agent_id != agent.id:
        raise ForbiddenError("This customer is not assigned to you.", "NOT_ASSIGNED")
    if loan.status == Loan.Status.CLOSED:
        raise DomainError("This loan is already fully repaid.", "LOAN_CLOSED")
    outstanding = loan.outstanding
    if amount > outstanding:
        raise DomainError(
            f"Amount ₹{amount} exceeds the outstanding balance of ₹{outstanding}.",
            "OVER_COLLECTION",
            {"outstanding": str(outstanding), "excess": str(amount - outstanding)},
        )

    window = timezone.now() - timedelta(minutes=settings.CMRS["DUPLICATE_WINDOW_MINUTES"])
    recent = (
        Collection.objects.filter(loan=loan, amount=amount, collected_at__gte=window)
        .exclude(status=Collection.Status.VOIDED)
        .first()
    )
    if recent and not confirm_duplicate:
        raise ConflictError(
            f"Receipt {recent.receipt_number} for the same amount was recorded on this loan "
            f"at {timezone.localtime(recent.collected_at):%H:%M}. Confirm if this is a separate payment.",
            "POSSIBLE_DUPLICATE",
            {"existing_receipt": recent.receipt_number, "existing_id": recent.id},
        )

    try:
        with transaction.atomic():
            collection = Collection.objects.create(
                receipt_number=next_document_number(
                    "RCP", loan.branch.code, on=timezone.localdate(collected_at) if collected_at else None),
                loan=loan,
                customer=loan.customer,
                agent=agent,
                branch=loan.branch,
                amount=amount,
                idempotency_key=idempotency_key,
                remarks=remarks,
                collected_at=collected_at or timezone.now(),
            )
    except IntegrityError:  # concurrent retry with the same key
        existing = Collection.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing, False
        raise

    for installment, allocated in apply_payment(loan, amount):
        RepaymentAllocation.objects.create(collection=collection, installment=installment, amount=allocated)

    audit.record(agent, "collection.recorded", collection, ref=collection.receipt_number, amount=amount,
                 loan=loan.loan_number, outstanding_after=loan.outstanding, duplicate_confirmed=bool(recent))
    return collection, True


@transaction.atomic
def void_collection(collection_id: int, *, actor, reason: str) -> Collection:
    """Cancel a receipt entered in error. Allowed only while the cash is still with the agent."""
    collection = Collection.objects.select_for_update().get(pk=collection_id)
    if actor.is_agent and collection.agent_id != actor.id:
        raise ForbiddenError("You can only void your own receipts.")
    if actor.is_manager and collection.branch_id != actor.branch_id:
        raise ForbiddenError("You can only void receipts of your own branch.")
    if collection.status != Collection.Status.COLLECTED:
        raise LockedRecordError(
            f"Receipt {collection.receipt_number} is {collection.get_status_display().lower()} and can no longer be voided."
        )
    if not reason.strip():
        raise DomainError("A reason is required to void a receipt.", "REASON_REQUIRED")

    loan = Loan.objects.select_for_update().get(pk=collection.loan_id)
    reverse_payment(loan, list(collection.allocations.all()))
    collection.status = Collection.Status.VOIDED
    collection.void_reason = reason.strip()
    collection.voided_at = timezone.now()
    collection.voided_by = actor
    collection.save()
    audit.record(actor, "collection.voided", collection, ref=collection.receipt_number, reason=reason,
                 amount=collection.amount)
    return collection


# --------------------------------------------------------------------------- hand-over to branch
@transaction.atomic
def submit_cash(*, agent, collection_ids: list[int], declared_amount, notes: str = "", as_of=None) -> CashSubmission:
    if not agent.is_agent:
        raise ForbiddenError("Only collection agents submit cash to a branch.")
    ids = set(collection_ids)
    if not ids:
        raise DomainError("Select at least one receipt to submit.", "EMPTY_SUBMISSION")

    collections = list(Collection.objects.select_for_update().filter(pk__in=ids))
    if len(collections) != len(ids):
        raise DomainError("One or more receipts were not found.", "RECEIPT_NOT_FOUND")
    for c in collections:
        if c.agent_id != agent.id:
            raise ForbiddenError(f"Receipt {c.receipt_number} was not collected by you.")
        if c.status != Collection.Status.COLLECTED:
            raise ConflictError(
                f"Receipt {c.receipt_number} is already {c.get_status_display().lower()}.", "RECEIPT_NOT_AVAILABLE",
                {"receipt": c.receipt_number, "status": c.status},
            )

    expected = sum((c.amount for c in collections), ZERO)
    declared = to_money(declared_amount)
    if declared < 0:
        raise DomainError("Declared amount cannot be negative.", "INVALID_AMOUNT")
    submission = CashSubmission.objects.create(
        submission_number=next_document_number("SUB", agent.branch.code, on=as_of),
        agent=agent,
        branch=agent.branch,
        expected_amount=expected,
        declared_amount=declared,
        agent_notes=notes,
    )
    submission.collections.set(collections)
    Collection.objects.filter(pk__in=ids).update(status=Collection.Status.SUBMITTED, updated_at=timezone.now())
    audit.record(agent, "submission.created", submission, ref=submission.submission_number, expected=expected,
                 declared=declared, receipts=[c.receipt_number for c in collections])
    return submission


def _lock_pending_submission(submission_id: int, actor) -> CashSubmission:
    submission = CashSubmission.objects.select_for_update(of=("self",)).select_related("agent", "branch").get(pk=submission_id)
    if actor.is_manager and submission.branch_id != actor.branch_id:
        raise ForbiddenError("You can only review submissions of your own branch.")
    if submission.status != CashSubmission.Status.PENDING:
        raise ConflictError(f"Submission {submission.submission_number} is already {submission.status.lower()}.",
                            "ALREADY_REVIEWED")
    return submission


@transaction.atomic
def approve_submission(submission_id: int, *, actor, received_amount, notes: str = "") -> CashSubmission:
    """
    Manager confirms the cash physically counted. Receipts move to BRANCH_RECEIVED.
    If the count differs from the receipts total, a SUBMISSION discrepancy is raised
    against the agent and notes become mandatory.
    """
    submission = _lock_pending_submission(submission_id, actor)
    received = to_money(received_amount)
    if received < 0:
        raise DomainError("Received amount cannot be negative.", "INVALID_AMOUNT")
    if received == 0:
        raise DomainError("Nothing was received. Reject the submission instead.", "USE_REJECT")
    difference = submission.expected_amount - received
    if difference != 0 and not notes.strip():
        raise DomainError("Explain the difference between expected and received cash.", "NOTES_REQUIRED",
                          {"difference": str(difference)})

    submission.received_amount = received
    submission.difference = difference
    submission.status = CashSubmission.Status.APPROVED
    submission.reviewed_by = actor
    submission.reviewed_at = timezone.now()
    submission.review_notes = notes.strip()
    submission.save()
    submission.collections.update(status=Collection.Status.BRANCH_RECEIVED, updated_at=timezone.now())

    raise_discrepancy(stage=Discrepancy.Stage.SUBMISSION, expected=submission.expected_amount, actual=received,
                      branch=submission.branch, agent=submission.agent, submission=submission, actor=actor,
                      reason=notes.strip())
    audit.record(actor, "submission.approved", submission, ref=submission.submission_number,
                 expected=submission.expected_amount, received=received, difference=difference)
    return submission


@transaction.atomic
def reject_submission(submission_id: int, *, actor, reason: str) -> CashSubmission:
    """Cash not accepted (e.g. counterfeit notes, wrong batch). Receipts return to the agent's custody."""
    submission = _lock_pending_submission(submission_id, actor)
    if not reason.strip():
        raise DomainError("A rejection reason is required.", "REASON_REQUIRED")
    submission.status = CashSubmission.Status.REJECTED
    submission.reviewed_by = actor
    submission.reviewed_at = timezone.now()
    submission.review_notes = reason.strip()
    submission.save()
    submission.collections.update(status=Collection.Status.COLLECTED, updated_at=timezone.now())
    audit.record(actor, "submission.rejected", submission, ref=submission.submission_number, reason=reason)
    return submission


def agent_cash_in_hand(agent) -> Decimal:
    return Collection.objects.filter(agent=agent, status=Collection.Status.COLLECTED).aggregate(
        s=Sum("amount"))["s"] or ZERO
