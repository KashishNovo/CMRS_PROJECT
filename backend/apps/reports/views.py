"""
Dashboard and summary reports.

Two kinds of figures:
* Flow  - what happened inside the date range (expected dues, collected, received, deposited, settled).
* Position - where money sits right now (with agents, at branch, in transit to bank, open discrepancies).

Filters: date_from, date_to, branch, agent, status (collection status). Every query is
scoped to the caller's role first, so a filter can only narrow, never widen, visibility.
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import scope_queryset
from apps.banking.models import BankDeposit
from apps.banking.services import depositable_submissions
from apps.cash.models import CashSubmission, Collection
from apps.core.models import Branch
from apps.lending.models import Installment, Loan
from apps.reconciliation.models import Discrepancy

ZERO = Decimal("0.00")
MONEY = DecimalField(max_digits=16, decimal_places=2)
LIVE = ~Q(status=Collection.Status.VOIDED)
STAGE_ORDER = [
    Collection.Status.COLLECTED,
    Collection.Status.SUBMITTED,
    Collection.Status.BRANCH_RECEIVED,
    Collection.Status.DEPOSITED,
    Collection.Status.SETTLED,
]

FILTER_PARAMS = [
    OpenApiParameter("date_from", OpenApiTypes.DATE, description="Default: first day of current month"),
    OpenApiParameter("date_to", OpenApiTypes.DATE, description="Default: today"),
    OpenApiParameter("branch", OpenApiTypes.INT),
    OpenApiParameter("agent", OpenApiTypes.INT),
    OpenApiParameter("status", OpenApiTypes.STR, description="Collection status"),
]


def money(value) -> str:
    return str((value if value is not None else ZERO).quantize(Decimal("0.01")))


def total(qs, field):
    return qs.aggregate(v=Coalesce(Sum(field), Value(ZERO), output_field=MONEY))["v"]


class Filters:
    def __init__(self, request):
        p = request.query_params
        today = timezone.localdate()
        self.user = request.user
        self.date_to = parse_date(p.get("date_to", "")) or today
        self.date_from = parse_date(p.get("date_from", "")) or self.date_to.replace(day=1)
        self.branch = p.get("branch") or None
        self.agent = p.get("agent") or None
        self.status = p.get("status") or None
        if self.user.is_agent:
            self.agent = self.user.pk

    def scoped(self, qs, *, branch_field="branch", agent_field=None):
        qs = scope_queryset(qs, self.user, branch_field=branch_field, agent_field=agent_field)
        if self.branch:
            qs = qs.filter(**{branch_field: self.branch})
        if self.agent and agent_field:
            qs = qs.filter(**{agent_field: self.agent})
        return qs

    def as_dict(self):
        return {"date_from": self.date_from, "date_to": self.date_to, "branch": self.branch, "agent": self.agent,
                "status": self.status}


def collections_qs(f: Filters):
    qs = f.scoped(Collection.objects.all(), agent_field="agent")
    if f.status:
        qs = qs.filter(status=f.status)
    return qs


class DashboardView(APIView):
    @extend_schema(parameters=FILTER_PARAMS, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        f = Filters(request)
        in_range = Q(collected_at__date__gte=f.date_from, collected_at__date__lte=f.date_to)
        collections = collections_qs(f)
        all_collections = f.scoped(Collection.objects.filter(LIVE), agent_field="agent")

        # ---- flow
        installments = f.scoped(Installment.objects.filter(due_date__gte=f.date_from, due_date__lte=f.date_to),
                                branch_field="loan__branch", agent_field="loan__customer__assigned_agent")
        expected = total(installments, "amount_due")
        expected_paid = total(installments, "amount_paid")
        collected_qs = collections.filter(in_range).filter(LIVE)
        collected = total(collected_qs, "amount")
        submissions = f.scoped(CashSubmission.objects.all(), agent_field="agent")
        received_qs = submissions.filter(status=CashSubmission.Status.APPROVED, reviewed_at__date__gte=f.date_from,
                                         reviewed_at__date__lte=f.date_to)
        deposits = BankDeposit.objects.none() if f.user.is_agent else f.scoped(BankDeposit.objects.all())
        deposited_qs = deposits.filter(deposit_date__gte=f.date_from, deposit_date__lte=f.date_to).exclude(
            status=BankDeposit.Status.FAILED)
        settled_qs = deposits.filter(settlement_date__gte=f.date_from, settlement_date__lte=f.date_to,
                                     status__in=[BankDeposit.Status.SETTLED, BankDeposit.Status.SETTLEMENT_MISMATCH])

        # ---- position (now)
        at_branch_qs = (
            CashSubmission.objects.none() if f.user.is_agent
            else f.scoped(CashSubmission.objects.filter(
                pk__in=CashSubmission.objects.filter(status=CashSubmission.Status.APPROVED)
                .exclude(deposits__status__in=BankDeposit.ACTIVE_STATUSES).values("pk")), agent_field="agent")
        )
        sla_cutoff = timezone.localdate() - timedelta(days=settings.CMRS["SETTLEMENT_SLA_DAYS"])
        in_transit = deposits.filter(status=BankDeposit.Status.PENDING_SETTLEMENT)
        delayed = in_transit.filter(deposit_date__lt=sla_cutoff)
        loans = f.scoped(Loan.objects.filter(status=Loan.Status.ACTIVE), agent_field="customer__assigned_agent")
        outstanding = loans.aggregate(v=Coalesce(Sum(F("total_payable") - F("total_paid")), Value(ZERO),
                                                 output_field=MONEY))["v"]
        discrepancies = f.scoped(Discrepancy.objects.all(), agent_field="agent")
        open_disc = discrepancies.filter(status=Discrepancy.Status.OPEN)

        # ---- lifecycle: how far did this period's receipts travel?
        by_status = dict(
            collected_qs.values_list("status").annotate(s=Coalesce(Sum("amount"), Value(ZERO), output_field=MONEY))
        )
        lifecycle, reached = [], ZERO
        for status in reversed(STAGE_ORDER):
            reached += by_status.get(status, ZERO)
            lifecycle.append({"stage": status, "label": Collection.Status(status).label, "amount": money(reached),
                              "at_stage": money(by_status.get(status, ZERO))})
        lifecycle.reverse()

        trend = (
            collected_qs.annotate(day=TruncDate("collected_at", tzinfo=timezone.get_current_timezone()))
            .values("day").annotate(amount=Sum("amount"), count=Count("id")).order_by("day")
        )
        due_trend = dict(installments.values_list("due_date").annotate(s=Sum("amount_due")))
        days, d = [], f.date_from
        collected_by_day = {row["day"]: row for row in trend}
        while d <= f.date_to and len(days) < 400:
            row = collected_by_day.get(d)
            days.append({"date": d, "collected": money(row["amount"] if row else ZERO),
                         "receipts": row["count"] if row else 0, "expected": money(due_trend.get(d, ZERO))})
            d += timedelta(days=1)

        return Response({
            "filters": f.as_dict(),
            "flow": {
                "expected": money(expected),
                "expected_paid": money(expected_paid),
                "collection_efficiency": (
                    str((expected_paid * 100 / expected).quantize(Decimal("0.1"))) if expected else None
                ),
                "collected": money(collected),
                "collected_count": collected_qs.count(),
                "received_at_branch": money(total(received_qs, "received_amount")),
                "deposited": money(total(deposited_qs, "amount")),
                "settled": money(total(settled_qs, "settled_amount")),
            },
            "position": {
                "cash_with_agents": money(total(all_collections.filter(status=Collection.Status.COLLECTED), "amount")),
                "pending_verification": money(total(all_collections.filter(status=Collection.Status.SUBMITTED),
                                                    "amount")),
                "cash_at_branch": money(total(at_branch_qs, "received_amount")),
                "in_transit_to_bank": money(total(in_transit, "amount")),
                "delayed_deposits": delayed.count(),
                "delayed_amount": money(total(delayed, "amount")),
                "outstanding": money(outstanding),
                "active_loans": loans.count(),
            },
            "discrepancies": {
                "open_count": open_disc.count(),
                "open_shortage": money(total(open_disc.filter(direction=Discrepancy.Direction.SHORTAGE), "amount")),
                "open_excess": money(total(open_disc.filter(direction=Discrepancy.Direction.EXCESS), "amount")),
                "by_stage": [
                    {"stage": row["stage"], "count": row["c"], "amount": money(row["s"])}
                    for row in open_disc.values("stage").annotate(c=Count("id"), s=Sum("amount")).order_by("stage")
                ],
            },
            "lifecycle": lifecycle,
            "trend": days,
        })


class BranchSummaryView(APIView):
    """One row per branch (managers see only theirs)."""

    @extend_schema(parameters=FILTER_PARAMS, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        f = Filters(request)
        branches = scope_queryset(Branch.objects.filter(is_active=True), request.user, branch_field="pk")
        if f.branch:
            branches = branches.filter(pk=f.branch)
        rng = dict(collected_at__date__gte=f.date_from, collected_at__date__lte=f.date_to)
        rows = []
        for b in branches:
            col = Collection.objects.filter(branch=b).filter(LIVE)
            if f.agent:
                col = col.filter(agent_id=f.agent)
            dep = BankDeposit.objects.filter(branch=b)
            rows.append({
                "branch": b.id, "code": b.code, "name": b.name,
                "collected": money(total(col.filter(**rng), "amount")),
                "receipts": col.filter(**rng).count(),
                "cash_with_agents": money(total(col.filter(status=Collection.Status.COLLECTED), "amount")),
                "pending_verification": money(total(col.filter(status=Collection.Status.SUBMITTED), "amount")),
                "cash_at_branch": money(total(depositable_submissions(b.id), "received_amount")),
                "deposited": money(total(dep.filter(deposit_date__gte=f.date_from, deposit_date__lte=f.date_to)
                                         .exclude(status=BankDeposit.Status.FAILED), "amount")),
                "settled": money(total(dep.filter(settlement_date__gte=f.date_from, settlement_date__lte=f.date_to),
                                       "settled_amount")),
                "open_discrepancies": Discrepancy.objects.filter(branch=b, status=Discrepancy.Status.OPEN).count(),
                "open_discrepancy_amount": money(total(
                    Discrepancy.objects.filter(branch=b, status=Discrepancy.Status.OPEN), "amount")),
            })
        return Response({"filters": f.as_dict(), "results": rows})


class AgentSummaryView(APIView):
    """One row per collection agent: performance and accountability."""

    @extend_schema(parameters=FILTER_PARAMS, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        f = Filters(request)
        agents = f.scoped(User.objects.filter(role=User.Role.AGENT, is_active=True), agent_field="pk")
        rng = dict(collected_at__date__gte=f.date_from, collected_at__date__lte=f.date_to)
        rows = []
        for a in agents.select_related("branch").order_by("branch__code", "first_name"):
            col = Collection.objects.filter(agent=a).filter(LIVE)
            due = Installment.objects.filter(loan__customer__assigned_agent=a, due_date__gte=f.date_from,
                                             due_date__lte=f.date_to)
            short = Discrepancy.objects.filter(agent=a, stage=Discrepancy.Stage.SUBMISSION)
            rows.append({
                "agent": a.id, "name": a.get_full_name() or a.username, "branch_code": a.branch.code if a.branch else None,
                "assigned_customers": a.assigned_customers.filter(is_active=True).count(),
                "expected": money(total(due, "amount_due")),
                "collected": money(total(col.filter(**rng), "amount")),
                "receipts": col.filter(**rng).count(),
                "cash_in_hand": money(total(col.filter(status=Collection.Status.COLLECTED), "amount")),
                "pending_verification": money(total(col.filter(status=Collection.Status.SUBMITTED), "amount")),
                "open_shortage": money(total(short.filter(status=Discrepancy.Status.OPEN,
                                                          direction=Discrepancy.Direction.SHORTAGE), "amount")),
                "rejected_submissions": CashSubmission.objects.filter(agent=a, status=CashSubmission.Status.REJECTED)
                .count(),
            })
        return Response({"filters": f.as_dict(), "results": rows})
