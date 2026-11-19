"""API key authentication shared by every ``/v1`` route.

Only the MUSEO backend calls this service; it sends ``X-API-Key: <AI_SERVICE_KEY>``.
"""

import hmac
from typing import Annotated

from fastapi import Depends, Security
from fastapi.security import APIKeyHeader

from app.core.config import Settings, get_settings
from app.core.errors import ErrorCode, ServiceError

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
