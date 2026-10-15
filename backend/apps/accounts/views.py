from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.core import audit
from apps.core.models import Branch

from .models import User
from .permissions import IsAdmin, read_any_write
from .serializers import BranchSerializer, LoginSerializer, LogoutSerializer, UserSerializer


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    throttle_scope = "login"


class LogoutView(APIView):
    """Blacklists the refresh token so it cannot mint new access tokens."""

    @extend_schema(request=LogoutSerializer, responses={205: None})
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError:
            pass  # already invalid: logging out is still a success
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class UserViewSet(viewsets.ModelViewSet):
    """
    Admins manage all users. Branch managers may *list* their branch's staff
    (needed to assign agents to customers) but cannot change anyone.
    """

    serializer_class = UserSerializer
    filterset_fields = ["role", "branch", "is_active"]
    search_fields = ["username", "first_name", "last_name", "email"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated()]
        return [IsAdmin()]

    def get_queryset(self):
        user = self.request.user
        qs = User.objects.select_related("branch")
        if not user.is_authenticated:
            return qs.none()
        if user.has_global_scope:
            return qs
        if user.is_manager:
            return qs.filter(branch=user.branch_id)
        return qs.filter(pk=user.pk)

    def perform_create(self, serializer):
        user = serializer.save()
        audit.record(self.request.user, "user.created", user, ref=user.username, role=user.role, branch=None)

    def perform_update(self, serializer):
        user = serializer.save()
        changed = {k: str(v) for k, v in serializer.validated_data.items() if k != "password"}
        audit.record(self.request.user, "user.updated", user, ref=user.username, branch=None,
                     password_reset="password" in serializer.validated_data, **changed)


class BranchViewSet(viewsets.ModelViewSet):
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer
    permission_classes = [read_any_write("ADMIN")]
    search_fields = ["code", "name", "city"]
    http_method_names = ["get", "post", "patch", "head", "options"]
