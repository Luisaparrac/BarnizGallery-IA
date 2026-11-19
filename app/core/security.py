"""API key authentication shared by every ``/v1`` route.

Only the MUSEO backend calls this service; it sends ``X-API-Key: <AI_SERVICE_KEY>``.
"""

import hmac
from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader

from app.core.config import Settings, get_settings
from app.core.errors import ErrorCode, ServiceError
from app.core.rate_limiter import client_identity

API_KEY_HEADER = "X-API-Key"

_api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


def require_api_key(
    api_key: Annotated[str | None, Security(_api_key_header)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Reject the request with 401 ``unauthorized`` unless the key matches."""
    expected = settings.ai_service_key.get_secret_value().encode()
    if not api_key or not hmac.compare_digest(api_key.encode(), expected):
        raise ServiceError(
            ErrorCode.UNAUTHORIZED, "Falta la clave del servicio (X-API-Key) o no es válida."
        )


def client_ip(request: Request) -> str:
    """Caller IP. Behind Render's proxy it comes first in ``X-Forwarded-For``."""
    forwarded = request.headers.get("x-forwarded-for", "")
    first = forwarded.split(",")[0].strip()
    if first:
        return first
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(
    request: Request,
    api_key: Annotated[str | None, Security(_api_key_header)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """429 ``rate_limited`` above ``RATE_LIMIT_PER_MINUTE`` requests per key and IP.

    It runs before the key check, so attempts with wrong keys are limited too.
    """
    limiter = request.app.state.rate_limiter
    wait = limiter.hit(client_identity(api_key, client_ip(request)), settings.rate_limit_per_minute)
    if wait is not None:
        raise ServiceError(
            ErrorCode.RATE_LIMITED,
            f"Demasiadas solicitudes. Intenta de nuevo en {wait} segundos.",
            headers={"Retry-After": str(wait)},
        )
