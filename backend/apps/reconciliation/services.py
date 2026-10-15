from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core import audit
from apps.core.exceptions import ConflictError, DomainError, ForbiddenError

from .models import Discrepancy


def raise_discrepancy(*, stage, expected: Decimal, actual: Decimal, branch, actor, reason="", agent=None,
                      submission=None, deposit=None) -> Discrepancy | None:
    """Create a discrepancy if `expected` and `actual` differ; returns None when they match."""
    diff = expected - actual
    if diff == 0:
        return None
    discrepancy = Discrepancy.objects.create(
        stage=stage,
        direction=Discrepancy.Direction.SHORTAGE if diff > 0 else Discrepancy.Direction.EXCESS,
        branch=branch,
        agent=agent,
        submission=submission,
        deposit=deposit,
        expected_amount=expected,
        actual_amount=actual,
        amount=abs(diff),
        reason=reason,
        raised_by=actor,
    )
    audit.record(actor, "discrepancy.raised", discrepancy, stage=stage, expected=expected, actual=actual,
                 amount=abs(diff), direction=discrepancy.direction)
    return discrepancy


@transaction.atomic
def resolve_discrepancy(discrepancy_id: int, *, actor, resolution: str, notes: str) -> Discrepancy:
    discrepancy = Discrepancy.objects.select_for_update().get(pk=discrepancy_id)
    if discrepancy.status == Discrepancy.Status.RESOLVED:
        raise ConflictError("This discrepancy is already resolved.", "ALREADY_RESOLVED")
    if actor.is_manager and discrepancy.branch_id != actor.branch_id:
        raise ForbiddenError("You can only resolve discrepancies of your own branch.")
    if actor.is_manager and discrepancy.stage == Discrepancy.Stage.SETTLEMENT:
        raise ForbiddenError("Bank settlement mismatches are resolved by Finance.")
    if not notes.strip():
        raise DomainError("Resolution notes are required.", "NOTES_REQUIRED")
    discrepancy.status = Discrepancy.Status.RESOLVED
    discrepancy.resolution = resolution
    discrepancy.resolution_notes = notes.strip()
    discrepancy.resolved_by = actor
    discrepancy.resolved_at = timezone.now()
    discrepancy.save()
    audit.record(actor, "discrepancy.resolved", discrepancy, resolution=resolution, notes=notes)
    return discrepancy
