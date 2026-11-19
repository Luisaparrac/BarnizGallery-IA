"""Common error format: ``{"code": "...", "message": "..."}``.

``code`` is a stable English identifier the backend can branch on; ``message`` is a
Spanish text meant for people.
"""

from enum import StrEnum

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.responses import Utf8JSONResponse


class ErrorCode(StrEnum):
    UNAUTHORIZED = "unauthorized"
    INVALID_REQUEST = "invalid_request"
    CONTENT_REJECTED = "content_rejected"
    NOT_ENOUGH_DATA = "not_enough_data"
    PROVIDER_ERROR = "provider_error"
    PROVIDER_TIMEOUT = "provider_timeout"
    FEATURE_DISABLED = "feature_disabled"


STATUS_BY_CODE: dict[ErrorCode, int] = {
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.INVALID_REQUEST: 400,
    ErrorCode.CONTENT_REJECTED: 400,
    ErrorCode.NOT_ENOUGH_DATA: 422,
    ErrorCode.PROVIDER_ERROR: 502,
    ErrorCode.PROVIDER_TIMEOUT: 504,
    ErrorCode.FEATURE_DISABLED: 503,
}


class ServiceError(Exception):
    """Expected error that is returned to the caller in the common format."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    @property
    def status_code(self) -> int:
        return STATUS_BY_CODE[self.code]


def error_response(status_code: int, code: ErrorCode, message: str) -> Utf8JSONResponse:
    return Utf8JSONResponse(status_code=status_code, content={"code": code, "message": message})


async def _handle_service_error(_: Request, exc: ServiceError) -> Utf8JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message)


async def _handle_validation_error(_: Request, exc: RequestValidationError) -> Utf8JSONResponse:
    message = "La solicitud no es válida."
    errors = exc.errors()
    if errors:
        location = ".".join(str(part) for part in errors[0].get("loc", ()) if part != "body")
        if location:
            message = f"La solicitud no es válida: revisa el campo '{location}'."
    return error_response(400, ErrorCode.INVALID_REQUEST, message)


async def _handle_http_error(_: Request, exc: StarletteHTTPException) -> Utf8JSONResponse:
    if exc.status_code == 401:
        return error_response(401, ErrorCode.UNAUTHORIZED, "No autorizado.")
    return error_response(
        exc.status_code, ErrorCode.INVALID_REQUEST, "La ruta o el método no son válidos."
    )


def register_error_handlers(app: FastAPI) -> None:
    """Make every expected error use the common JSON format."""
    app.add_exception_handler(ServiceError, _handle_service_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)
