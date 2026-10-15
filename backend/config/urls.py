from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.views import BranchViewSet, LoginView, LogoutView, MeView, UserViewSet
from apps.banking.views import DepositViewSet
from apps.cash.views import CollectionViewSet, SubmissionViewSet
from apps.lending.views import CustomerViewSet, LoanViewSet
from apps.reconciliation.views import AuditLogViewSet, DiscrepancyViewSet
from apps.reports.views import AgentSummaryView, BranchSummaryView, DashboardView

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("branches", BranchViewSet, basename="branch")
router.register("customers", CustomerViewSet, basename="customer")
router.register("loans", LoanViewSet, basename="loan")
router.register("collections", CollectionViewSet, basename="collection")
router.register("submissions", SubmissionViewSet, basename="submission")
router.register("deposits", DepositViewSet, basename="deposit")
router.register("discrepancies", DiscrepancyViewSet, basename="discrepancy")
router.register("audit-logs", AuditLogViewSet, basename="auditlog")


def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health),
    path("api/auth/login/", LoginView.as_view(), name="login"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("api/auth/logout/", LogoutView.as_view(), name="logout"),
    path("api/auth/me/", MeView.as_view(), name="me"),
    path("api/reports/dashboard/", DashboardView.as_view(), name="dashboard"),
    path("api/reports/branches/", BranchSummaryView.as_view(), name="branch-summary"),
    path("api/reports/agents/", AgentSummaryView.as_view(), name="agent-summary"),
    path("api/", include(router.urls)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
