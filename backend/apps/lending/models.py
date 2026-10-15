from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.core.models import MoneyField, TimeStampedModel


class Customer(TimeStampedModel):
    customer_code = models.CharField(max_length=30, unique=True, editable=False)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, db_index=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    id_number = models.CharField("KYC / ID number", max_length=40, blank=True)
    branch = models.ForeignKey("core.Branch", on_delete=models.PROTECT, related_name="customers")
    assigned_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_customers",
        limit_choices_to={"role": "AGENT"},
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["full_name"]
        indexes = [models.Index(fields=["branch", "assigned_agent"])]

    def __str__(self):
        return f"{self.customer_code} {self.full_name}"


class Loan(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        CLOSED = "CLOSED", "Closed (fully repaid)"

    loan_number = models.CharField(max_length=30, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="loans")
    branch = models.ForeignKey("core.Branch", on_delete=models.PROTECT, related_name="loans")
    principal = MoneyField()
    annual_interest_rate = models.DecimalField(max_digits=5, decimal_places=2, help_text="% per annum, reducing balance")
    tenure_months = models.PositiveSmallIntegerField()
    disbursement_date = models.DateField(default=timezone.localdate)
    emi_amount = MoneyField()
    total_payable = MoneyField(help_text="Principal + scheduled interest")
    total_paid = MoneyField(default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(name="loan_principal_positive", condition=Q(principal__gt=0)),
            models.CheckConstraint(name="loan_rate_non_negative", condition=Q(annual_interest_rate__gte=0)),
            models.CheckConstraint(name="loan_tenure_positive", condition=Q(tenure_months__gt=0)),
            # Database-level guard against over-collection.
            models.CheckConstraint(
                name="loan_paid_within_payable", condition=Q(total_paid__gte=0) & Q(total_paid__lte=F("total_payable"))
            ),
        ]

    def __str__(self):
        return self.loan_number

    @property
    def outstanding(self):
        return self.total_payable - self.total_paid


class Installment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PARTIALLY_PAID = "PARTIALLY_PAID", "Partially paid"
        PAID = "PAID", "Paid"

    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name="installments")
    installment_number = models.PositiveSmallIntegerField()
    due_date = models.DateField(db_index=True)
    principal_component = MoneyField()
    interest_component = MoneyField()
    amount_due = MoneyField()
    amount_paid = MoneyField(default=0)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING, db_index=True)

    class Meta:
        ordering = ["loan", "installment_number"]
        constraints = [
            models.UniqueConstraint(fields=["loan", "installment_number"], name="unique_installment_number"),
            models.CheckConstraint(
                name="installment_paid_within_due", condition=Q(amount_paid__gte=0) & Q(amount_paid__lte=F("amount_due"))
            ),
        ]

    def __str__(self):
        return f"{self.loan.loan_number} #{self.installment_number}"

    @property
    def balance(self):
        return self.amount_due - self.amount_paid

    @property
    def is_overdue(self):
        return self.status != self.Status.PAID and self.due_date < timezone.localdate()

    def refresh_status(self):
        if self.amount_paid <= 0:
            self.status = self.Status.PENDING
        elif self.amount_paid < self.amount_due:
            self.status = self.Status.PARTIALLY_PAID
        else:
            self.status = self.Status.PAID
