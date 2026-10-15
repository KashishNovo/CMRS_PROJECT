from datetime import timedelta

import django_filters
from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsFinanceOrAdmin, IsManager, scope_queryset
from apps.cash.models import CashSubmission
from apps.cash.serializers import ReasonSerializer, SubmissionListSerializer
from apps.core.filters import DateRangeFilterSet

from . import services
from .models import BankDeposit
from .serializers import DepositCreateSerializer, DepositListSerializer, DepositSerializer, SettleSerializer


class DepositFilter(DateRangeFilterSet):
    date_field = "deposit_date"
    delayed = django_filters.BooleanFilter(method="filter_delayed")

    class Meta:
        model = BankDeposit
        fields = ["status", "branch"]

    def filter_delayed(self, qs, name, value):
        cutoff = timezone.localdate() - timedelta(days=settings.CMRS["SETTLEMENT_SLA_DAYS"])
        delayed = qs.filter(status=BankDeposit.Status.PENDING_SETTLEMENT, deposit_date__lt=cutoff)
        return delayed if value else qs.exclude(pk__in=delayed.values("pk"))


class DepositViewSet(viewsets.ReadOnlyModelViewSet):
    filterset_class = DepositFilter
    search_fields = ["deposit_number", "reference_number", "bank_name"]
    ordering_fields = ["deposit_date", "amount", "created_at"]

    def get_serializer_class(self):
        return DepositListSerializer if self.action == "list" else DepositSerializer

    def get_queryset(self):
        user = self.request.user
        qs = BankDeposit.objects.select_related("branch", "created_by", "settled_by")
        if self.action != "list":
            qs = qs.prefetch_related("submissions__agent", "submissions__branch", "submissions__deposits")
        if getattr(user, "is_agent", True):
            return qs.none()
        return scope_queryset(qs, user)

    @extend_schema(request=DepositCreateSerializer, responses={201: DepositSerializer})
    def create(self, request):
        if not IsManager().has_permission(request, self):
            self.permission_denied(request, message="Only branch managers create bank deposits.")
        s = DepositCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        deposit = services.create_deposit(actor=request.user, **s.validated_data)
        return Response(DepositSerializer(self.get_queryset().get(pk=deposit.pk)).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=SubmissionListSerializer(many=True))
    @action(detail=False, url_path="available-submissions", permission_classes=[IsManager])
    def available_submissions(self, request):
        """Approved cash submissions at my branch that are not yet in a live deposit."""
        qs = services.depositable_submissions(request.user.branch_id).select_related("agent", "branch", "reviewed_by")
        return Response(SubmissionListSerializer(qs.order_by("created_at"), many=True).data)

    @extend_schema(request=SettleSerializer, responses=DepositSerializer)
    @action(detail=True, methods=["post"], permission_classes=[IsFinanceOrAdmin])
    def settle(self, request, pk=None):
        deposit = self.get_object()
        s = SettleSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.settle_deposit(deposit.pk, actor=request.user, **s.validated_data)
        return Response(DepositSerializer(self.get_queryset().get(pk=deposit.pk)).data)

    @extend_schema(request=ReasonSerializer, responses=DepositSerializer)
    @action(detail=True, methods=["post"], permission_classes=[IsFinanceOrAdmin])
    def fail(self, request, pk=None):
        deposit = self.get_object()
        s = ReasonSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.fail_deposit(deposit.pk, actor=request.user, reason=s.validated_data["reason"])
        return Response(DepositSerializer(self.get_queryset().get(pk=deposit.pk)).data)
