"""
A Discrepancy is raised automatically whenever two figures that should agree don't:

    SUBMISSION  receipts total (expected)   vs cash counted at branch   -> agent short/excess
    DEPOSIT     branch-reconciled cash      vs deposit slip amount      -> branch short/excess
    SETTLEMENT  deposit slip amount         vs bank statement credit    -> bank short/excess

It stays OPEN until someone with authority records how it was resolved.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import MoneyField, TimeStampedModel


class Discrepancy(TimeStampedModel):
    class Stage(models.TextChoices):
        SUBMISSION = "SUBMISSION", "Agent → Branch"
        DEPOSIT = "DEPOSIT", "Branch → Bank"
        SETTLEMENT = "SETTLEMENT", "Bank → Company account"

    class Direction(models.TextChoices):
        SHORTAGE = "SHORTAGE", "Shortage"
        EXCESS = "EXCESS", "Excess"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        RESOLVED = "RESOLVED", "Resolved"

    class Resolution(models.TextChoices):
        RECOVERED = "RECOVERED", "Recovered from responsible party"
        WRITTEN_OFF = "WRITTEN_OFF", "Written off"
        BANK_CORRECTED = "BANK_CORRECTED", "Corrected by bank"
        REFUNDED = "REFUNDED", "Excess refunded / adjusted"
        OTHER = "OTHER", "Other"

    stage = models.CharField(max_length=12, choices=Stage.choices, db_index=True)
    direction = models.CharField(max_length=10, choices=Direction.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)
    branch = models.ForeignKey("core.Branch", on_delete=models.PROTECT, related_name="discrepancies")
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="discrepancies")
    submission = models.ForeignKey("cash.CashSubmission", null=True, blank=True, on_delete=models.PROTECT, related_name="discrepancies")
    deposit = models.ForeignKey("banking.BankDeposit", null=True, blank=True, on_delete=models.PROTECT, related_name="discrepancies")
    expected_amount = MoneyField()
    actual_amount = MoneyField()
    amount = MoneyField(help_text="Absolute difference")
    reason = models.CharField(max_length=500, blank=True)
    raised_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    resolution = models.CharField(max_length=20, choices=Resolution.choices, blank=True)
    resolution_notes = models.CharField(max_length=500, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "discrepancies"
        constraints = [
            models.CheckConstraint(name="discrepancy_amount_positive", condition=Q(amount__gt=0)),
            models.CheckConstraint(
                name="discrepancy_has_source", condition=Q(submission__isnull=False) | Q(deposit__isnull=False)
            ),
            models.CheckConstraint(
                name="resolved_discrepancy_has_resolution", condition=~Q(status="RESOLVED") | ~Q(resolution="")
            ),
        ]

    def __str__(self):
        return f"{self.get_stage_display()} {self.direction} {self.amount}"
