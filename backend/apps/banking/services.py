"""Branch -> bank deposit, and Finance's settlement confirmation against the bank statement."""
from django.db import IntegrityError, transaction
from django.db.models.functions import Lower
from django.utils import timezone

from apps.cash.models import CashSubmission, Collection
from apps.core import audit
from apps.core.exceptions import ConflictError, DomainError, ForbiddenError
from apps.core.models import next_document_number
from apps.core.money import ZERO, to_money
from apps.reconciliation.models import Discrepancy
from apps.reconciliation.services import raise_discrepancy

from .models import BankDeposit


def depositable_submissions(branch_id):
    """Approved submissions whose cash is still at the branch (not in a live deposit)."""
    return (
        CashSubmission.objects.filter(branch_id=branch_id, status=CashSubmission.Status.APPROVED)
        .exclude(deposits__status__in=BankDeposit.ACTIVE_STATUSES)
        .distinct()
    )


def _assert_reference_unique(bank_name: str, reference: str):
    exists = BankDeposit.objects.annotate(b=Lower("bank_name"), r=Lower("reference_number")).filter(
        b=bank_name.lower(), r=reference.lower()
    )
    if exists.exists():
        raise ConflictError(
            f"Reference {reference} at {bank_name} is already recorded on deposit {exists.first().deposit_number}.",
            "DUPLICATE_BANK_REFERENCE",
        )


@transaction.atomic
def create_deposit(*, actor, submission_ids: list[int], bank_name: str, account_number: str, reference_number: str,
                   deposit_date, amount, mismatch_reason: str = "") -> BankDeposit:
    if not actor.is_manager:
        raise ForbiddenError("Only branch managers create bank deposits.")
    if deposit_date > timezone.localdate():
        raise DomainError("Deposit date cannot be in the future.", "INVALID_DATE")
    bank_name, reference_number = bank_name.strip(), reference_number.strip()
    if not reference_number:
        raise DomainError("Bank reference number is required.", "REFERENCE_REQUIRED")
    ids = set(submission_ids)
    if not ids:
        raise DomainError("Select at least one approved cash submission.", "EMPTY_DEPOSIT")

    submissions = list(CashSubmission.objects.select_for_update().filter(pk__in=ids))
    available = set(depositable_submissions(actor.branch_id).filter(pk__in=ids).values_list("pk", flat=True))
    if len(submissions) != len(ids) or available != ids:
        bad = sorted(s.submission_number for s in submissions if s.pk not in available)
        raise ConflictError("Some submissions are not available for deposit (not approved, other branch, or already "
                            "deposited).", "SUBMISSION_NOT_AVAILABLE", {"submissions": bad})

    _assert_reference_unique(bank_name, reference_number)

    reconciled = sum((s.received_amount for s in submissions), ZERO)
    amount = to_money(amount)
    if amount <= 0:
        raise DomainError("Deposit amount must be greater than zero.", "INVALID_AMOUNT")
    difference = reconciled - amount
    if difference != 0 and not mismatch_reason.strip():
        raise DomainError(
            f"Deposit amount differs from reconciled cash (₹{reconciled}) by ₹{abs(difference)}. Give a reason.",
            "DEPOSIT_MISMATCH", {"reconciled": str(reconciled), "difference": str(difference)},
        )

    try:
        with transaction.atomic():
            deposit = BankDeposit.objects.create(
                deposit_number=next_document_number("DEP", actor.branch.code, on=deposit_date),
                branch=actor.branch,
                bank_name=bank_name,
                account_number=account_number.strip(),
                reference_number=reference_number,
                deposit_date=deposit_date,
                reconciled_amount=reconciled,
                amount=amount,
                deposit_difference=difference,
                mismatch_reason=mismatch_reason.strip(),
                created_by=actor,
            )
    except IntegrityError:
        raise ConflictError(f"Reference {reference_number} is already recorded.", "DUPLICATE_BANK_REFERENCE")
    deposit.submissions.set(submissions)
    Collection.objects.filter(submissions__in=submissions, status=Collection.Status.BRANCH_RECEIVED).update(
        status=Collection.Status.DEPOSITED, updated_at=timezone.now()
    )
    raise_discrepancy(stage=Discrepancy.Stage.DEPOSIT, expected=reconciled, actual=amount, branch=actor.branch,
                      deposit=deposit, actor=actor, reason=mismatch_reason.strip())
    audit.record(actor, "deposit.created", deposit, ref=deposit.deposit_number, amount=amount, reconciled=reconciled,
                 reference=reference_number, bank=bank_name, submissions=[s.submission_number for s in submissions])
    return deposit


def _lock_pending_deposit(deposit_id: int) -> BankDeposit:
    deposit = BankDeposit.objects.select_for_update(of=("self",)).select_related("branch").get(pk=deposit_id)
    if deposit.status != BankDeposit.Status.PENDING_SETTLEMENT:
        raise ConflictError(f"Deposit {deposit.deposit_number} is already {deposit.get_status_display().lower()}.",
                            "ALREADY_SETTLED")
    return deposit


@transaction.atomic
def settle_deposit(deposit_id: int, *, actor, settled_amount, settlement_date, settlement_reference: str = "",
                   notes: str = "") -> BankDeposit:
    """Finance matches the deposit against the bank statement credit."""
    if not actor.has_global_scope:
        raise ForbiddenError("Only Finance can confirm settlements.")
    deposit = _lock_pending_deposit(deposit_id)
    settled = to_money(settled_amount)
    if settled <= 0:
        raise DomainError("Settled amount must be greater than zero. Use 'Mark failed' if nothing was credited.",
                          "INVALID_AMOUNT")
    if settlement_date < deposit.deposit_date:
        raise DomainError("Settlement date cannot be before the deposit date.", "INVALID_DATE")
    if settlement_date > timezone.localdate():
        raise DomainError("Settlement date cannot be in the future.", "INVALID_DATE")
    difference = deposit.amount - settled
    if difference != 0 and not notes.strip():
        raise DomainError(f"Bank credit differs from the deposit by ₹{abs(difference)}. Add notes.", "NOTES_REQUIRED",
                          {"difference": str(difference)})

    deposit.settled_amount = settled
    deposit.settlement_date = settlement_date
    deposit.settlement_reference = settlement_reference.strip()
    deposit.settlement_difference = difference
    deposit.settlement_notes = notes.strip()
    deposit.settled_by = actor
    deposit.settled_at = timezone.now()
    deposit.status = BankDeposit.Status.SETTLED if difference == 0 else BankDeposit.Status.SETTLEMENT_MISMATCH
    deposit.save()
    Collection.objects.filter(submissions__deposits=deposit, status=Collection.Status.DEPOSITED).update(
        status=Collection.Status.SETTLED, updated_at=timezone.now()
    )
    raise_discrepancy(stage=Discrepancy.Stage.SETTLEMENT, expected=deposit.amount, actual=settled,
                      branch=deposit.branch, deposit=deposit, actor=actor, reason=notes.strip())
    audit.record(actor, "deposit.settled", deposit, ref=deposit.deposit_number, settled=settled,
                 difference=difference, status=deposit.status)
    return deposit


@transaction.atomic
def fail_deposit(deposit_id: int, *, actor, reason: str) -> BankDeposit:
    """
    The bank did not credit the deposit (returned / rejected slip). The cash is treated as
    back at the branch: receipts return to BRANCH_RECEIVED and the submissions become
    available for a fresh deposit with a new bank reference.
    """
    if not actor.has_global_scope:
        raise ForbiddenError("Only Finance can mark a deposit as failed.")
    deposit = _lock_pending_deposit(deposit_id)
    if not reason.strip():
        raise DomainError("A failure reason is required.", "REASON_REQUIRED")
    deposit.status = BankDeposit.Status.FAILED
    deposit.failure_reason = reason.strip()
    deposit.settled_by = actor
    deposit.settled_at = timezone.now()
    deposit.save()
    Collection.objects.filter(submissions__deposits=deposit, status=Collection.Status.DEPOSITED).update(
        status=Collection.Status.BRANCH_RECEIVED, updated_at=timezone.now()
    )
    audit.record(actor, "deposit.failed", deposit, ref=deposit.deposit_number, reason=reason)
    return deposit
