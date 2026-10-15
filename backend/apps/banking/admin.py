from django.contrib import admin

from apps.core.admin import ReadOnlyAdmin

from .models import BankDeposit


@admin.register(BankDeposit)
class BankDepositAdmin(ReadOnlyAdmin):
    list_display = ["deposit_number", "branch", "bank_name", "reference_number", "amount", "settled_amount", "status"]
    list_filter = ["status", "branch"]
    search_fields = ["deposit_number", "reference_number"]
