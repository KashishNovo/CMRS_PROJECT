"""
Cash custody chain:  Collection (receipt) -> CashSubmission (agent hands cash to branch).

Collection.status follows the money:
    COLLECTED -> SUBMITTED -> BRANCH_RECEIVED -> DEPOSITED -> SETTLED
                   |  (rejected)                   | (deposit failed)
                   v                               v
               COLLECTED                     BRANCH_RECEIVED
    COLLECTED -> VOIDED (only before the cash leaves the agent)
"""
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import GuardedModel, MoneyField, TimeStampedModel
from django.utils import timezone


class Collection(GuardedModel, TimeStampedModel):
    class Status(models.TextChoices):
        COLLECTED = "COLLECTED", "Collected (with agent)"
        SUBMITTED = "SUBMITTED", "Submitted to branch"
        BRANCH_RECEIVED = "BRANCH_RECEIVED", "Received at branch"
        DEPOSITED = "DEPOSITED", "Deposited in bank"
        SETTLED = "SETTLED", "Settled"
        VOIDED = "VOIDED", "Voided"

    class Mode(models.TextChoices):
        CASH = "CASH", "Cash"

    LOCKED_STATUSES = {Status.SUBMITTED, Status.BRANCH_RECEIVED, Status.DEPOSITED, Status.SETTLED, Status.VOIDED}
    PROTECTED_FIELDS = ("amount", "loan_id", "customer_id", "agent_id", "branch_id", "collected_at", "receipt_number")

    receipt_number = models.CharField(max_length=40, unique=True, editable=False)
    loan = models.ForeignKey("lending.Loan", on_delete=models.PROTECT, related_name="collections")
    customer = models.ForeignKey("lending.Customer", on_delete=models.PROTECT, related_name="collections")
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="collections")
    branch = models.ForeignKey("core.Branch", on_delete=models.PROTECT, related_name="collections")
    amount = MoneyField()
    payment_mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.CASH)
    collected_at = models.DateTimeField(default=timezone.now, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.COLLECTED, db_index=True)
    idempotency_key = models.UUIDField(null=True, blank=True, unique=True,
                                       help_text="Client-generated key; a retried request returns the original receipt.")
    remarks = models.CharField(max_length=255, blank=True)
    void_reason = models.CharField(max_length=255, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-collected_at", "-id"]
        constraints = [models.CheckConstraint(name="collection_amount_positive", condition=Q(amount__gt=0))]
        indexes = [
            models.Index(fields=["branch", "status"]),
            models.Index(fields=["agent", "status"]),
            models.Index(fields=["loan", "collected_at"]),
        ]

    def __str__(self):
        return self.receipt_number

    def is_locked(self):
        return self.status in self.LOCKED_STATUSES


class RepaymentAllocation(models.Model):
    """How each receipt was applied to the loan's instalments (oldest first)."""

    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name="allocations")
    installment = models.ForeignKey("lending.Installment", on_delete=models.PROTECT, related_name="allocations")
    amount = MoneyField()

    class Meta:
        constraints = [models.CheckConstraint(name="allocation_amount_positive", condition=Q(amount__gt=0))]


class CashSubmission(GuardedModel, TimeStampedModel):
    """An agent handing a batch of receipts' cash to the branch; verified by the branch manager."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending verification"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    PROTECTED_FIELDS = ("expected_amount", "declared_amount", "received_amount", "difference", "agent_id", "branch_id")

    submission_number = models.CharField(max_length=40, unique=True, editable=False)
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cash_submissions")
    branch = models.ForeignKey("core.Branch", on_delete=models.PROTECT, related_name="cash_submissions")
    collections = models.ManyToManyField(Collection, related_name="submissions")
    expected_amount = MoneyField(help_text="Sum of the receipts in this batch (system figure)")
    declared_amount = MoneyField(help_text="Cash the agent says they are handing over")
    received_amount = MoneyField(null=True, blank=True, help_text="Cash physically counted by the branch manager")
    difference = MoneyField(null=True, blank=True, help_text="expected - received; positive = shortage")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    agent_notes = models.CharField(max_length=255, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(name="submission_expected_positive", condition=Q(expected_amount__gt=0)),
            models.CheckConstraint(name="submission_declared_non_negative", condition=Q(declared_amount__gte=0)),
            models.CheckConstraint(
                name="submission_received_non_negative",
                condition=Q(received_amount__isnull=True) | Q(received_amount__gte=0),
            ),
            models.CheckConstraint(
                name="approved_submission_has_count",
                condition=~Q(status="APPROVED") | Q(received_amount__isnull=False),
            ),
        ]

    def __str__(self):
        return self.submission_number

    def is_locked(self):
        return self.status != self.Status.PENDING
