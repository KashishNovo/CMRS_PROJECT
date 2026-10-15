from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrator"
        FINANCE = "FINANCE", "Finance / Treasury"
        BRANCH_MANAGER = "BRANCH_MANAGER", "Branch Manager"
        AGENT = "AGENT", "Collection Agent"

    BRANCH_ROLES = {Role.BRANCH_MANAGER, Role.AGENT}

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.AGENT, db_index=True)
    branch = models.ForeignKey(
        "core.Branch", null=True, blank=True, on_delete=models.PROTECT, related_name="staff"
    )
    phone = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["username"]
        constraints = [
            models.CheckConstraint(
                name="branch_staff_have_branch",
                condition=~models.Q(role__in=["BRANCH_MANAGER", "AGENT"]) | models.Q(branch__isnull=False),
            )
        ]

    def clean(self):
        super().clean()
        if self.role in self.BRANCH_ROLES and not self.branch_id:
            raise ValidationError({"branch": "Branch managers and agents must belong to a branch."})

    # Convenience predicates used by permissions and query scoping.
    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_finance(self):
        return self.role == self.Role.FINANCE

    @property
    def is_manager(self):
        return self.role == self.Role.BRANCH_MANAGER

    @property
    def is_agent(self):
        return self.role == self.Role.AGENT

    @property
    def has_global_scope(self):
        """Admins and finance see every branch; others are confined to theirs."""
        return self.is_admin or self.is_finance

    def __str__(self):
        return self.get_full_name() or self.username
