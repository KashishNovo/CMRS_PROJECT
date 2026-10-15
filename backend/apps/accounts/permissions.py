"""
Role-based access control.

Two layers:
1. `HasRole` permission classes decide *which endpoints* a role may call.
2. `scope_queryset` decides *which rows* a user may see (branch / own records),
   so a branch manager can never read or act on another branch's data even with a guessed id.
"""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import User

R = User.Role


def has_role(*roles):
    class _HasRole(BasePermission):
        allowed = set(roles)

        def has_permission(self, request, view):
            user = request.user
            return bool(user and user.is_authenticated and (user.is_superuser or user.role in self.allowed))

    _HasRole.__name__ = "HasRole_" + "_".join(roles)
    return _HasRole


IsAdmin = has_role(R.ADMIN)
IsAgent = has_role(R.AGENT)
IsManager = has_role(R.BRANCH_MANAGER)
IsManagerOrAdmin = has_role(R.BRANCH_MANAGER, R.ADMIN)
IsFinanceOrAdmin = has_role(R.FINANCE, R.ADMIN)
IsReviewer = has_role(R.BRANCH_MANAGER, R.FINANCE, R.ADMIN)


class ReadAnyWriteRoles(BasePermission):
    """Any authenticated user can read (rows are scoped); only `write_roles` can write."""

    write_roles: set[str] = set()

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return user.is_superuser or user.role in self.write_roles


def read_any_write(*roles):
    return type("ReadAnyWrite_" + "_".join(roles), (ReadAnyWriteRoles,), {"write_roles": set(roles)})


def scope_queryset(qs, user, *, branch_field="branch", agent_field=None):
    """Restrict rows to what `user` may see."""
    if not getattr(user, "is_authenticated", False):  # e.g. schema generation
        return qs.none()
    if user.has_global_scope:
        return qs
    if user.is_manager:
        return qs.filter(**{branch_field: user.branch_id})
    if user.is_agent and agent_field:
        return qs.filter(**{agent_field: user})
    if user.is_agent:
        return qs.filter(**{branch_field: user.branch_id})
    return qs.none()
