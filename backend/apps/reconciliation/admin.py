from django.contrib import admin

from apps.core.admin import ReadOnlyAdmin

from .models import Discrepancy


@admin.register(Discrepancy)
class DiscrepancyAdmin(ReadOnlyAdmin):
    list_display = ["created_at", "stage", "direction", "amount", "branch", "agent", "status"]
    list_filter = ["stage", "status", "branch"]
