from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from .exceptions import LockedRecordError


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class MoneyField(models.DecimalField):
    """INR amount: NUMERIC(14, 2). Never a float."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_digits", 14)
        kwargs.setdefault("decimal_places", 2)
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, "django.db.models.DecimalField", args, kwargs


class GuardedModel(models.Model):
    """
    Blocks edits to financial fields once a record reaches a locked (reconciled) state.

    Status changes still go through the service layer, but amounts, parties and
    references of a reconciled record cannot be altered by any code path that uses
    the ORM's save()/delete(). The most sensitive columns are additionally protected
    by PostgreSQL triggers (see the cash and banking migrations).
    """

    PROTECTED_FIELDS: tuple[str, ...] = ()

    class Meta:
        abstract = True

    def is_locked(self) -> bool:  # overridden by subclasses
        return False

    def save(self, *args, **kwargs):
        if self.pk and self.PROTECTED_FIELDS:
            original = type(self).objects.filter(pk=self.pk).first()
            if original is not None and original.is_locked():
                changed = [f for f in self.PROTECTED_FIELDS if getattr(original, f) != getattr(self, f)]
                if changed:
                    raise LockedRecordError(
                        f"{type(self).__name__} {self.pk} is reconciled; fields {', '.join(changed)} cannot be modified."
                    )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.is_locked():
            raise LockedRecordError(f"{type(self).__name__} {self.pk} is reconciled and cannot be deleted.")
        return super().delete(*args, **kwargs)


class Branch(TimeStampedModel):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=120)
    city = models.CharField(max_length=80, blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        verbose_name_plural = "branches"

    def __str__(self):
        return f"{self.code} - {self.name}"


class DocumentSequence(models.Model):
    """Gap-free counters for human-readable document numbers (receipts, deposits...)."""

    key = models.CharField(max_length=64, unique=True)
    last_value = models.PositiveBigIntegerField(default=0)

    def __str__(self):
        return f"{self.key}={self.last_value}"


def next_document_number(prefix: str, scope: str = "", *, daily: bool = True, width: int = 5, on=None) -> str:
    """
    e.g. next_document_number("RCP", "MUM01") -> "RCP-MUM01-20261015-00007".

    The counter row is locked with SELECT ... FOR UPDATE, so two agents recording a
    receipt at the same instant can never receive the same number.
    """
    parts = [prefix]
    if scope:
        parts.append(scope)
    if daily:
        parts.append((on or timezone.localdate()).strftime("%Y%m%d"))
    key = "-".join(parts)
    with transaction.atomic():
        DocumentSequence.objects.get_or_create(key=key)
        seq = DocumentSequence.objects.select_for_update().get(key=key)
        seq.last_value += 1
        seq.save(update_fields=["last_value"])
    return f"{key}-{seq.last_value:0{width}d}"


class AuditLog(models.Model):
    """Append-only trail of every state change on a financial record."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=60, db_index=True)
    entity_type = models.CharField(max_length=60, db_index=True)
    entity_id = models.CharField(max_length=40, db_index=True)
    entity_ref = models.CharField(max_length=60, blank=True, help_text="Human readable number, e.g. a receipt no.")
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["entity_type", "entity_id"])]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.entity_type}#{self.entity_id}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise LockedRecordError("Audit log entries are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LockedRecordError("Audit log entries are append-only.")
