"""
Domain errors and the single API error envelope.

Every error response has the shape:
    {"error": {"code": "OVER_COLLECTION", "message": "...", "details": {...}}}
so the frontend can branch on `code` and show `message` as-is.
"""
import logging

from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404
from rest_framework import exceptions as drf_exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger("cmrs.api")


class DomainError(Exception):
    """A business rule was violated. Raised by the service layer, never swallowed."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "BUSINESS_RULE_VIOLATION"

    def __init__(self, message: str, code: str | None = None, details: dict | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        self.details = details or {}
        if status_code:
            self.status_code = status_code


class ConflictError(DomainError):
    """The request conflicts with the current state (duplicate, already processed...)."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "CONFLICT"


class LockedRecordError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "RECORD_LOCKED"


class ForbiddenError(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "FORBIDDEN"


def _envelope(code: str, message: str, details=None, http_status=400) -> Response:
    return Response({"error": {"code": code, "message": message, "details": details or {}}}, status=http_status)


def api_exception_handler(exc, context):
    if isinstance(exc, DomainError):
        logger.info("domain error %s: %s", exc.code, exc.message)
        return _envelope(exc.code, exc.message, exc.details, exc.status_code)

    if isinstance(exc, DjangoValidationError):
        details = exc.message_dict if hasattr(exc, "message_dict") else {"non_field_errors": exc.messages}
        return _envelope("VALIDATION_ERROR", "Please correct the highlighted fields.", details, 400)

    if isinstance(exc, IntegrityError):
        # Safety net: DB constraints back up every service-level check.
        logger.warning("integrity error: %s", exc)
        return _envelope("CONSTRAINT_VIOLATION", "The change conflicts with existing data.", {}, 409)

    if isinstance(exc, Http404):
        exc = drf_exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = drf_exceptions.PermissionDenied()

    response = exception_handler(exc, context)
    if response is None:
        logger.exception("unhandled error", exc_info=exc)
        return _envelope("SERVER_ERROR", "Something went wrong. The error has been logged.", {}, 500)

    if isinstance(exc, drf_exceptions.ValidationError):
        code, message, details = "VALIDATION_ERROR", "Please correct the highlighted fields.", response.data
    else:
        code = getattr(exc, "default_code", "error").upper()
        message = str(getattr(exc, "detail", exc))
        details = {}
    response.data = {"error": {"code": code, "message": message, "details": details}}
    return response
