from decimal import Decimal
from datetime import date, datetime

from .middleware import current_ip
from .models import AuditLog


def _jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def record(actor, action: str, obj, *, ref: str = "", branch=None, **changes) -> AuditLog:
    return AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        entity_type=type(obj).__name__,
        entity_id=str(obj.pk),
        entity_ref=ref,
        branch=branch if branch is not None else getattr(obj, "branch", None),
        changes=_jsonable(changes),
        ip_address=current_ip(),
    )
