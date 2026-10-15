from django.contrib import admin

from apps.core.admin import ReadOnlyAdmin

from .models import Customer, Installment, Loan


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ["customer_code", "full_name", "phone", "branch", "assigned_agent", "is_active"]
    list_filter = ["branch", "is_active"]
    search_fields = ["customer_code", "full_name", "phone"]
    readonly_fields = ["customer_code"]


class InstallmentInline(admin.TabularInline):
    model = Installment
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in Installment._meta.fields]


@admin.register(Loan)
class LoanAdmin(ReadOnlyAdmin):
    list_display = ["loan_number", "customer", "branch", "principal", "total_payable", "total_paid", "status"]
    list_filter = ["branch", "status"]
    search_fields = ["loan_number", "customer__full_name"]
    inlines = [InstallmentInline]
