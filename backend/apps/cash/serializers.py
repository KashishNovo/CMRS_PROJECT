from decimal import Decimal

from rest_framework import serializers

from .models import CashSubmission, Collection, RepaymentAllocation


class AllocationSerializer(serializers.ModelSerializer):
    installment_number = serializers.IntegerField(source="installment.installment_number", read_only=True)
    due_date = serializers.DateField(source="installment.due_date", read_only=True)

    class Meta:
        model = RepaymentAllocation
        fields = ["installment_number", "due_date", "amount"]


class CollectionSerializer(serializers.ModelSerializer):
    loan_number = serializers.CharField(source="loan.loan_number", read_only=True)
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    customer_code = serializers.CharField(source="customer.customer_code", read_only=True)
    agent_name = serializers.SerializerMethodField()
    branch_code = serializers.CharField(source="branch.code", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    allocations = AllocationSerializer(many=True, read_only=True)
    loan_outstanding = serializers.DecimalField(source="loan.outstanding", max_digits=14, decimal_places=2,
                                                read_only=True)

    class Meta:
        model = Collection
        fields = [
            "id", "receipt_number", "loan", "loan_number", "customer", "customer_name", "customer_code", "agent",
            "agent_name", "branch", "branch_code", "amount", "payment_mode", "collected_at", "status",
            "status_display", "remarks", "void_reason", "voided_at", "allocations", "loan_outstanding",
        ]
        read_only_fields = fields

    def get_agent_name(self, obj) -> str | None:
        return obj.agent.get_full_name() or obj.agent.username


class CollectionCreateSerializer(serializers.Serializer):
    loan = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    remarks = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    idempotency_key = serializers.UUIDField(required=False, allow_null=True)
    confirm_duplicate = serializers.BooleanField(required=False, default=False)


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


class SubmissionSerializer(serializers.ModelSerializer):
    agent_name = serializers.SerializerMethodField()
    branch_code = serializers.CharField(source="branch.code", read_only=True)
    reviewed_by_name = serializers.SerializerMethodField()
    receipt_count = serializers.IntegerField(read_only=True, default=None)
    collections = CollectionSerializer(many=True, read_only=True)
    deposit_numbers = serializers.SerializerMethodField()

    class Meta:
        model = CashSubmission
        fields = [
            "id", "submission_number", "agent", "agent_name", "branch", "branch_code", "expected_amount",
            "declared_amount", "received_amount", "difference", "status", "agent_notes", "reviewed_by_name",
            "reviewed_at", "review_notes", "created_at", "receipt_count", "collections", "deposit_numbers",
        ]
        read_only_fields = fields

    def get_agent_name(self, obj) -> str | None:
        return obj.agent.get_full_name() or obj.agent.username

    def get_reviewed_by_name(self, obj) -> str | None:
        return str(obj.reviewed_by) if obj.reviewed_by else None

    def get_deposit_numbers(self, obj) -> list[str]:
        return [d.deposit_number for d in obj.deposits.all()]


class SubmissionListSerializer(SubmissionSerializer):
    class Meta(SubmissionSerializer.Meta):
        fields = [f for f in SubmissionSerializer.Meta.fields if f != "collections"]
        read_only_fields = fields


class SubmissionCreateSerializer(serializers.Serializer):
    collection_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False, max_length=500)
    declared_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.00"))
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class ApproveSubmissionSerializer(serializers.Serializer):
    received_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.00"))
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
