"""
Bank deposits of reconciled branch cash, and their settlement in the company account.

    PENDING_SETTLEMENT -> SETTLED              (bank credit == deposit)
                       -> SETTLEMENT_MISMATCH  (bank credit != deposit, discrepancy raised)
                       -> FAILED               (deposit returned / not credited; cash goes back to branch)
A PENDING_SETTLEMENT deposit older than CMRS["SETTLEMENT_SLA_DAYS"] is reported as delayed.
"""
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

from apps.core.models import GuardedModel, MoneyField, TimeStampedModel


class BankDeposit(GuardedModel, TimeStampedModel):
    class Status(models.TextChoices):
        PENDING_SETTLEMENT = "PENDING_SETTLEMENT", "Awaiting settlement"
        SETTLED = "SETTLED", "Settled"
        SETTLEMENT_MISMATCH = "SETTLEMENT_MISMATCH", "Settled with mismatch"
        FAILED = "FAILED", "Failed"

    ACTIVE_STATUSES = (Status.PENDING_SETTLEMENT, Status.SETTLED, Status.SETTLEMENT_MISMATCH)
    PROTECTED_FIELDS = (
        "amount", "reconciled_amount", "bank_name", "reference_number", "deposit_date", "branch_id",
        "settled_amount", "settlement_date",
    )

    deposit_number = models.CharField(max_length=40, unique=True, editable=False)
    branch = models.ForeignKey("core.Branch", on_delete=models.PROTECT, related_name="bank_deposits")
    submissions = models.ManyToManyField("cash.CashSubmission", related_name="deposits")
    bank_name = models.CharField(max_length=80)
    account_number = models.CharField(max_length=30, blank=True, help_text="Company account credited")
    reference_number = models.CharField(max_length=60, help_text="Bank transaction / deposit slip reference")
    deposit_date = models.DateField()
    reconciled_amount = MoneyField(help_text="Cash verified at branch for the selected submissions")
    amount = MoneyField(help_text="Amount on the deposit slip")
    deposit_difference = MoneyField(default=0, help_text="reconciled - deposited; positive = short deposit")
    mismatch_reason = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.PENDING_SETTLEMENT, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    settled_amount = MoneyField(null=True, blank=True, help_text="Amount credited per bank statement")
    settlement_date = models.DateField(null=True, blank=True)
    settlement_reference = models.CharField(max_length=60, blank=True)
    settlement_difference = MoneyField(null=True, blank=True, help_text="deposited - settled; positive = short credit")
    settlement_notes = models.CharField(max_length=500, blank=True)
    settled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    settled_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-deposit_date", "-id"]
        constraints = [
            models.CheckConstraint(name="deposit_amount_positive", condition=Q(amount__gt=0)),
            models.CheckConstraint(
                name="settled_amount_non_negative", condition=Q(settled_amount__isnull=True) | Q(settled_amount__gte=0)
            ),
            # The same bank reference can never be recorded twice (case-insensitive).
            models.UniqueConstraint(Lower("bank_name"), Lower("reference_number"), name="unique_bank_reference"),
        ]

    def __str__(self):
        return self.deposit_number

    def is_locked(self):
        return self.status != self.Status.PENDING_SETTLEMENT

    @property
    def is_delayed(self):
        sla = settings.CMRS["SETTLEMENT_SLA_DAYS"]
        return self.status == self.Status.PENDING_SETTLEMENT and self.deposit_date < timezone.localdate() - timedelta(days=sla)
