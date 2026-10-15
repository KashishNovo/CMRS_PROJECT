from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from apps.accounts.permissions import IsReviewer, scope_queryset
from apps.core.filters import DateRangeFilterSet
from apps.core.models import AuditLog

from . import services
from .models import Discrepancy


class DiscrepancySerializer(serializers.ModelSerializer):
    branch_code = serializers.CharField(source="branch.code", read_only=True)
    agent_name = serializers.SerializerMethodField()
    stage_display = serializers.CharField(source="get_stage_display", read_only=True)
    submission_number = serializers.CharField(source="submission.submission_number", read_only=True, default=None)
    deposit_number = serializers.CharField(source="deposit.deposit_number", read_only=True, default=None)
    raised_by_name = serializers.SerializerMethodField()
    resolved_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Discrepancy
        fields = [
            "id", "stage", "stage_display", "direction", "status", "branch", "branch_code", "agent", "agent_name",
            "submission", "submission_number", "deposit", "deposit_number", "expected_amount", "actual_amount",
            "amount", "reason", "raised_by_name", "created_at", "resolution", "resolution_notes", "resolved_by_name",
            "resolved_at",
        ]
        read_only_fields = fields

    def get_agent_name(self, obj) -> str | None:
        return str(obj.agent) if obj.agent else None

    def get_raised_by_name(self, obj) -> str | None:
        return str(obj.raised_by) if obj.raised_by else None

    def get_resolved_by_name(self, obj) -> str | None:
        return str(obj.resolved_by) if obj.resolved_by else None


class ResolveSerializer(serializers.Serializer):
    resolution = serializers.ChoiceField(choices=Discrepancy.Resolution.choices)
    notes = serializers.CharField(max_length=500)


class DiscrepancyFilter(DateRangeFilterSet):
    class Meta:
        model = Discrepancy
        fields = ["stage", "status", "direction", "branch", "agent"]


class DiscrepancyViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DiscrepancySerializer
    filterset_class = DiscrepancyFilter
    ordering_fields = ["created_at", "amount"]

    def get_queryset(self):
        qs = Discrepancy.objects.select_related("branch", "agent", "submission", "deposit", "raised_by", "resolved_by")
        return scope_queryset(qs, self.request.user, agent_field="agent")

    @extend_schema(request=ResolveSerializer, responses=DiscrepancySerializer)
    @action(detail=True, methods=["post"], permission_classes=[IsReviewer])
    def resolve(self, request, pk=None):
        discrepancy = self.get_object()
        s = ResolveSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.resolve_discrepancy(discrepancy.pk, actor=request.user, resolution=s.validated_data["resolution"],
                                     notes=s.validated_data["notes"])
        return Response(DiscrepancySerializer(self.get_queryset().get(pk=discrepancy.pk)).data)


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    branch_code = serializers.CharField(source="branch.code", read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = ["id", "created_at", "actor", "actor_name", "action", "entity_type", "entity_id", "entity_ref",
                  "branch", "branch_code", "changes", "ip_address"]
        read_only_fields = fields

    def get_actor_name(self, obj) -> str | None:
        return str(obj.actor) if obj.actor else "system"


class AuditLogFilter(DateRangeFilterSet):
    class Meta:
        model = AuditLog
        fields = ["action", "entity_type", "entity_id", "actor", "branch"]


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    filterset_class = AuditLogFilter
    permission_classes = [IsReviewer]
    search_fields = ["entity_ref", "action"]

    def get_queryset(self):
        return scope_queryset(AuditLog.objects.select_related("actor", "branch"), self.request.user)
