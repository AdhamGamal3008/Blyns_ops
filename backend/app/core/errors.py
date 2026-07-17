"""Error envelope & exceptions (docs/ARCHITECTURE.md §4).

Every error the API returns — domain errors, validation errors, plain HTTP
errors — is rendered in the single envelope:

    { "error": { "code": "...", "message": "...", "details": {} } }
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Reserved codes used across the specs.
TENANT_BLOCKED = "TENANT_BLOCKED"
USER_BLOCKED = "USER_BLOCKED"
ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
SEAT_LIMIT_REACHED = "SEAT_LIMIT_REACHED"
PERMISSION_DENIED = "PERMISSION_DENIED"
TENANT_NOT_FOUND = "TENANT_NOT_FOUND"
RATE_LIMITED = "RATE_LIMITED"
PROVISIONING_FAILED = "PROVISIONING_FAILED"
VALIDATION_ERROR = "VALIDATION_ERROR"
INVALID_CREDENTIALS = "INVALID_CREDENTIALS"  # generic login failure, reveals nothing
INSUFFICIENT_STOCK = "INSUFFICIENT_STOCK"  # docs/modules/INVENTORY.md §2

# Generic HTTP fallbacks (uniform envelope even for non-domain errors).
_HTTP_STATUS_CODES: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: VALIDATION_ERROR,
    429: RATE_LIMITED,
    500: "INTERNAL_ERROR",
}


class DomainError(Exception):
    """Base class for all business-rule errors."""

    def __init__(
        self,
        code: str,
        message: str,
        http_status: int = 400,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details or {}
        self.headers = headers or {}


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=error_body(exc.code, exc.message, exc.details),
            headers=exc.headers or None,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_body(
                VALIDATION_ERROR,
                "Request validation failed.",
                {"errors": exc.errors()},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = _HTTP_STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(code, str(exc.detail)),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=error_body("INTERNAL_ERROR", "An internal error occurred."),
        )
