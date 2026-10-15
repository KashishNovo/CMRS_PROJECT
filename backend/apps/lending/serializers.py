from decimal import Decimal

from rest_framework import serializers

from apps.accounts.models import User
from apps.cash.models import Collection
from apps.core.models import Branch

from .models import Customer, Installment, Loan


class CustomerSerializer(serializers.ModelSerializer):
    branch_code = serializers.CharField(source="branch.code", read_only=True)
    assigned_agent_name = serializers.SerializerMethodField()
    outstanding = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True, default=Decimal("0.00"))
    active_loans = serializers.IntegerField(read_only=True, default=0)
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.filter(is_active=True), required=False)
    assigned_agent = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role=User.Role.AGENT, is_active=True), required=False, allow_null=True
    )

    class Meta:
        model = Customer
        fields = [
            "id", "customer_code", "full_name", "phone", "email", "address", "id_number", "branch", "branch_code",
            "assigned_agent", "assigned_agent_name", "is_active", "outstanding", "active_loans", "created_at",
        ]
        read_only_fields = ["customer_code", "created_at"]

    def get_assigned_agent_name(self, obj) -> str | None:
        return str(obj.assigned_agent) if obj.assigned_agent else None

    def validate_phone(self, value):
        digits = value.replace(" ", "").replace("-", "")
        if not digits.lstrip("+").isdigit() or not 10 <= len(digits.lstrip("+")) <= 13:
            raise serializers.ValidationError("Enter a valid phone number.")
        return digits


class InstallmentSerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Installment
        fields = [
            "id", "installment_number", "due_date", "principal_component", "interest_component", "amount_due",
            "amount_paid", "balance", "status", "is_overdue",
        ]


class LoanSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    customer_code = serializers.CharField(source="customer.customer_code", read_only=True)
    branch_code = serializers.CharField(source="branch.code", read_only=True)
    outstanding = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    overdue_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True, default=Decimal("0.00"))
    next_due_date = serializers.DateField(read_only=True, default=None)
    next_due_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True, default=None)

    class Meta:
        model = Loan
        fields = [
            "id", "loan_number", "customer", "customer_name", "customer_code", "branch", "branch_code", "principal",
            "annual_interest_rate", "tenure_months", "disbursement_date", "emi_amount", "total_payable", "total_paid",
            "outstanding", "overdue_amount", "next_due_date", "next_due_amount", "status", "created_at",
        ]
        read_only_fields = fields


class LoanCreateSerializer(serializers.Serializer):
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())
    principal = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("1000.00"),
                                         max_value=Decimal("10000000.00"))
    annual_interest_rate = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal("0"),
                                                    max_value=Decimal("60"))
    tenure_months = serializers.IntegerField(min_value=1, max_value=120)
    disbursement_date = serializers.DateField()


class SchedulePreviewSerializer(serializers.Serializer):
    principal = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("1000.00"))
    annual_interest_rate = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal("0"),
                                                    max_value=Decimal("60"))
    tenure_months = serializers.IntegerField(min_value=1, max_value=120)
    disbursement_date = serializers.DateField()


class RepaymentHistorySerializer(serializers.ModelSerializer):
    agent_name = serializers.CharField(source="agent.get_full_name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Collection
        fields = ["id", "receipt_number", "amount", "collected_at", "agent_name", "status", "status_display",
                  "void_reason"]
