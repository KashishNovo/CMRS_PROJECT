"""Makes the client IP available to the audit logger without threading it through every call."""
from contextvars import ContextVar

_client_ip: ContextVar[str | None] = ContextVar("client_ip", default=None)


def current_ip() -> str | None:
    return _client_ip.get()


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")
        token = _client_ip.set(ip or None)
        try:
            return self.get_response(request)
        finally:
            _client_ip.reset(token)
