from decimal import Decimal

from django.db.models import Count, DecimalField, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsManagerOrAdmin, read_any_write, scope_queryset
from apps.core.exceptions import ForbiddenError

from . import services
from .models import Customer, Installment, Loan
from .serializers import (
    CustomerSerializer,
    InstallmentSerializer,
    LoanCreateSerializer,
    LoanSerializer,
    RepaymentHistorySerializer,
    SchedulePreviewSerializer,
)

MONEY = DecimalField(max_digits=14, decimal_places=2)
ZERO = Value(Decimal("0.00"), output_field=MONEY)


def scoped_customers(user):
    return scope_queryset(Customer.objects.all(), user, agent_field="assigned_agent")


class CustomerViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerSerializer
    permission_classes = [read_any_write("ADMIN", "BRANCH_MANAGER")]
    filterset_fields = ["branch", "assigned_agent", "is_active"]
    search_fields = ["full_name", "phone", "customer_code"]
    ordering_fields = ["full_name", "created_at", "outstanding"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        active = Q(loans__status=Loan.Status.ACTIVE)
        return (
            scoped_customers(self.request.user)
            .select_related("branch", "assigned_agent")
            .annotate(
                outstanding=Coalesce(Sum(F("loans__total_payable") - F("loans__total_paid"), filter=active), ZERO),
                active_loans=Count("loans", filter=active),
            )
            .order_by("full_name", "id")
        )

    def _check_branch(self, data):
        user = self.request.user
        if user.is_manager:
            if data.get("branch") and data["branch"].id != user.branch_id:
                raise ForbiddenError("You can only manage customers of your own branch.")
            data["branch"] = user.branch
        elif not data.get("branch"):
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"branch": "Branch is required."})
        return data

    def perform_create(self, serializer):
        data = self._check_branch(dict(serializer.validated_data))
        serializer.instance = services.create_customer(actor=self.request.user, **data)

    def perform_update(self, serializer):
        data = dict(serializer.validated_data)
        if self.request.user.is_manager and "branch" in data and data["branch"].id != self.request.user.branch_id:
            raise ForbiddenError("You can only manage customers of your own branch.")
        serializer.instance = services.update_customer(serializer.instance, actor=self.request.user, **data)


class LoanViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [read_any_write("ADMIN", "BRANCH_MANAGER")]
    filterset_fields = ["customer", "branch", "status"]
    search_fields = ["loan_number", "customer__full_name", "customer__customer_code"]
    ordering_fields = ["created_at", "principal", "disbursement_date"]

    def get_serializer_class(self):
        return LoanCreateSerializer if self.action == "create" else LoanSerializer

    def get_queryset(self):
        today = timezone.localdate()
        next_inst = Installment.objects.filter(loan=OuterRef("pk")).exclude(status=Installment.Status.PAID).order_by(
            "installment_number")
        qs = scope_queryset(Loan.objects.all(), self.request.user, agent_field="customer__assigned_agent")
        return qs.select_related("customer", "branch").annotate(
            overdue_amount=Coalesce(
                Sum(F("installments__amount_due") - F("installments__amount_paid"),
                    filter=Q(installments__due_date__lt=today) & ~Q(installments__status=Installment.Status.PAID)),
                ZERO,
            ),
            next_due_date=Subquery(next_inst.values("due_date")[:1]),
            next_due_amount=Subquery(next_inst.annotate(b=F("amount_due") - F("amount_paid")).values("b")[:1]),
        )

    def create(self, request, *args, **kwargs):
        serializer = LoanCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = serializer.validated_data["customer"]
        if not scoped_customers(request.user).filter(pk=customer.pk).exists():
            raise ForbiddenError("You can only create loans for customers of your own branch.")
        loan = services.create_loan(actor=request.user, **serializer.validated_data)
        return Response(LoanSerializer(self.get_queryset().get(pk=loan.pk)).data, status=status.HTTP_201_CREATED)

    @action(detail=True)
    def schedule(self, request, pk=None):
        loan = self.get_object()
        return Response(InstallmentSerializer(loan.installments.all(), many=True).data)

    @action(detail=True)
    def repayments(self, request, pk=None):
        loan = self.get_object()
        qs = loan.collections.select_related("agent").order_by("-collected_at")
        return Response(RepaymentHistorySerializer(qs, many=True).data)

    @extend_schema(request=SchedulePreviewSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"], url_path="preview-schedule", permission_classes=[IsManagerOrAdmin])
    def preview_schedule(self, request):
        s = SchedulePreviewSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        rows = services.build_schedule(d["principal"], d["annual_interest_rate"], d["tenure_months"],
                                       d["disbursement_date"])
        total = sum((r.amount for r in rows), Decimal("0.00"))
        return Response({
            "emi_amount": str(rows[0].amount),
            "total_payable": str(total),
            "total_interest": str(total - d["principal"]),
            "installments": [
                {"installment_number": r.number, "due_date": r.due_date, "principal_component": str(r.principal),
                 "interest_component": str(r.interest), "amount_due": str(r.amount)}
                for r in rows
            ],
        })
