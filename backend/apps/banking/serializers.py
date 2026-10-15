from decimal import Decimal

from rest_framework import serializers

from apps.cash.serializers import SubmissionListSerializer

from .models import BankDeposit


class DepositSerializer(serializers.ModelSerializer):
    branch_code = serializers.CharField(source="branch.code", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    is_delayed = serializers.BooleanField(read_only=True)
    created_by_name = serializers.SerializerMethodField()
    settled_by_name = serializers.SerializerMethodField()
    submissions = SubmissionListSerializer(many=True, read_only=True)

    class Meta:
        model = BankDeposit
        fields = [
            "id", "deposit_number", "branch", "branch_code", "bank_name", "account_number", "reference_number",
            "deposit_date", "reconciled_amount", "amount", "deposit_difference", "mismatch_reason", "status",
            "status_display", "is_delayed", "created_by_name", "created_at", "settled_amount", "settlement_date",
            "settlement_reference", "settlement_difference", "settlement_notes", "settled_by_name", "settled_at",
            "failure_reason", "submissions",
        ]
        read_only_fields = fields

    def get_created_by_name(self, obj) -> str | None:
        return str(obj.created_by) if obj.created_by else None

    def get_settled_by_name(self, obj) -> str | None:
        return str(obj.settled_by) if obj.settled_by else None


class DepositListSerializer(DepositSerializer):
    class Meta(DepositSerializer.Meta):
        fields = [f for f in DepositSerializer.Meta.fields if f != "submissions"]
        read_only_fields = fields


class DepositCreateSerializer(serializers.Serializer):
    submission_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False, max_length=200)
    bank_name = serializers.CharField(max_length=80)
    account_number = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    reference_number = serializers.CharField(max_length=60)
    deposit_date = serializers.DateField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    mismatch_reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class SettleSerializer(serializers.Serializer):
    settled_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.00"))
    settlement_date = serializers.DateField()
    settlement_reference = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
