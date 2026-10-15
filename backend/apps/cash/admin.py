from django.contrib import admin

from apps.core.admin import ReadOnlyAdmin

from .models import CashSubmission, Collection


@admin.register(Collection)
class CollectionAdmin(ReadOnlyAdmin):
    list_display = ["receipt_number", "collected_at", "agent", "customer", "amount", "status", "branch"]
    list_filter = ["status", "branch"]
    search_fields = ["receipt_number", "customer__full_name"]


@admin.register(CashSubmission)
class CashSubmissionAdmin(ReadOnlyAdmin):
    list_display = ["submission_number", "agent", "branch", "expected_amount", "received_amount", "status"]
    list_filter = ["status", "branch"]
