from decimal import Decimal

import django_filters
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsAgent, IsManagerOrAdmin, has_role, scope_queryset
from apps.core.filters import DateRangeFilterSet

from . import services
from .models import CashSubmission, Collection
from .serializers import (
    ApproveSubmissionSerializer,
    CollectionCreateSerializer,
    CollectionSerializer,
    ReasonSerializer,
    SubmissionCreateSerializer,
    SubmissionListSerializer,
    SubmissionSerializer,
)

ZERO = Decimal("0.00")


class CollectionFilter(DateRangeFilterSet):
    date_field = "collected_at"
    status = django_filters.MultipleChoiceFilter(choices=Collection.Status.choices)

    class Meta:
        model = Collection
        fields = ["status", "agent", "branch", "loan", "customer"]


class CollectionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Cash receipts. Agents record (POST) and void; everyone else reads within their scope.
    POST is idempotent when `idempotency_key` is sent: a retry returns the original receipt with 200.
    """

    serializer_class = CollectionSerializer
    filterset_class = CollectionFilter
    search_fields = ["receipt_number", "customer__full_name", "loan__loan_number"]
    ordering_fields = ["collected_at", "amount"]

    def get_queryset(self):
        qs = Collection.objects.select_related("loan", "customer", "agent", "branch").prefetch_related(
            "allocations__installment")
        return scope_queryset(qs, self.request.user, agent_field="agent")

    @extend_schema(request=CollectionCreateSerializer, responses={201: CollectionSerializer, 200: CollectionSerializer})
    def create(self, request):
        if not IsAgent().has_permission(request, self):
            self.permission_denied(request, message="Only collection agents can record collections.")
        s = CollectionCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        collection, created = services.record_collection(
            agent=request.user, loan_id=d["loan"], amount=d["amount"], idempotency_key=d.get("idempotency_key"),
            remarks=d["remarks"], confirm_duplicate=d["confirm_duplicate"],
        )
        data = CollectionSerializer(self.get_queryset().get(pk=collection.pk)).data
        return Response(data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @extend_schema(request=ReasonSerializer, responses=CollectionSerializer)
    @action(detail=True, methods=["post"], permission_classes=[has_role("AGENT", "BRANCH_MANAGER", "ADMIN")])
    def void(self, request, pk=None):
        collection = self.get_object()  # scope check
        s = ReasonSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.void_collection(collection.pk, actor=request.user, reason=s.validated_data["reason"])
        return Response(CollectionSerializer(self.get_queryset().get(pk=collection.pk)).data)

    @extend_schema(
        parameters=[OpenApiParameter("date", OpenApiTypes.DATE), OpenApiParameter("agent", OpenApiTypes.INT)],
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, url_path="daily-summary")
    def daily_summary(self, request):
        """Collections for one day (default today), plus cash the agent(s) currently hold."""
        day = parse_date(request.query_params.get("date", "")) or timezone.localdate()
        qs = self.get_queryset()
        if request.query_params.get("agent"):
            qs = qs.filter(agent_id=request.query_params["agent"])
        today = qs.filter(collected_at__date=day).exclude(status=Collection.Status.VOIDED)
        totals = today.aggregate(total=Sum("amount"), count=Count("id"))
        held = qs.filter(status=Collection.Status.COLLECTED).aggregate(s=Sum("amount"), c=Count("id"))
        pending = qs.filter(status=Collection.Status.SUBMITTED).aggregate(s=Sum("amount"))
        by_status = {
            row["status"]: {"count": row["count"], "amount": str(row["amount"])}
            for row in today.values("status").annotate(count=Count("id"), amount=Sum("amount"))
        }
        return Response({
            "date": day,
            "collected_count": totals["count"],
            "collected_amount": str(totals["total"] or ZERO),
            "cash_in_hand": str(held["s"] or ZERO),
            "cash_in_hand_receipts": held["c"],
            "pending_verification": str(pending["s"] or ZERO),
            "by_status": by_status,
        })


class SubmissionFilter(DateRangeFilterSet):
    class Meta:
        model = CashSubmission
        fields = ["status", "agent", "branch"]


class SubmissionViewSet(viewsets.ReadOnlyModelViewSet):
    filterset_class = SubmissionFilter
    search_fields = ["submission_number", "agent__first_name", "agent__last_name"]
    ordering_fields = ["created_at", "expected_amount"]

    def get_serializer_class(self):
        return SubmissionListSerializer if self.action == "list" else SubmissionSerializer

    def get_queryset(self):
        qs = CashSubmission.objects.select_related("agent", "branch", "reviewed_by").prefetch_related("deposits")
        if self.action != "list":
            qs = qs.prefetch_related("collections__loan", "collections__customer", "collections__agent",
                                     "collections__branch", "collections__allocations__installment")
        qs = qs.annotate(receipt_count=Count("collections", distinct=True))
        return scope_queryset(qs, self.request.user, agent_field="agent")

    @extend_schema(request=SubmissionCreateSerializer, responses={201: SubmissionSerializer})
    def create(self, request):
        if not IsAgent().has_permission(request, self):
            self.permission_denied(request, message="Only collection agents submit cash.")
        s = SubmissionCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        submission = services.submit_cash(agent=request.user, **s.validated_data)
        return Response(SubmissionSerializer(self.get_queryset().get(pk=submission.pk)).data,
                        status=status.HTTP_201_CREATED)

    @extend_schema(request=ApproveSubmissionSerializer, responses=SubmissionSerializer)
    @action(detail=True, methods=["post"], permission_classes=[IsManagerOrAdmin])
    def approve(self, request, pk=None):
        submission = self.get_object()
        s = ApproveSubmissionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.approve_submission(submission.pk, actor=request.user, **s.validated_data)
        return Response(SubmissionSerializer(self.get_queryset().get(pk=submission.pk)).data)

    @extend_schema(request=ReasonSerializer, responses=SubmissionSerializer)
    @action(detail=True, methods=["post"], permission_classes=[IsManagerOrAdmin])
    def reject(self, request, pk=None):
        submission = self.get_object()
        s = ReasonSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.reject_submission(submission.pk, actor=request.user, reason=s.validated_data["reason"])
        return Response(SubmissionSerializer(self.get_queryset().get(pk=submission.pk)).data)
