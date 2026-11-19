"""Error responses documented in OpenAPI (``/docs``), with one example per code."""

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.core.responses import Utf8JSONResponse
from app.schemas.errors import ErrorResponse

MEDIA_TYPE = Utf8JSONResponse.media_type

ERRORS: dict[str, tuple[int, str]] = {
    "unauthorized": (401, "Falta la clave del servicio (X-API-Key) o no es válida."),
    "invalid_request": (400, "La solicitud no es válida: revisa el campo 'title'."),
    "payload_too_large": (413, "La solicitud es demasiado grande."),
    "content_rejected": (
        400,
        "El pedido no se puede generar por su contenido. Cambia la descripción e inténtalo de "
        "nuevo.",
    ),
    "not_enough_data": (
        422,
        "Se necesitan al menos 3 piezas comparables en USD para sugerir un precio; llegaron 2.",
    ),
    "rate_limited": (429, "Demasiadas solicitudes. Intenta de nuevo en 42 segundos."),
    "budget_exceeded": (
        429,
        "Se alcanzó el límite diario de 30 imágenes. Intenta de nuevo mañana.",
    ),
    "provider_error": (502, "El generador de imágenes falló. Inténtalo de nuevo más tarde."),
    "feature_disabled": (503, "El servicio de IA no está configurado."),
    "provider_timeout": (
        504,
        "El generador de imágenes tardó demasiado. Inténtalo de nuevo más tarde.",
    ),
}

DESCRIPTIONS = {
    400: "Solicitud inválida o contenido rechazado.",
    401: "Falta `X-API-Key` o no es válida.",
    413: "Cuerpo demasiado grande (`MAX_REQUEST_BYTES`). Código `invalid_request`.",
    422: "No hay datos suficientes.",
    429: "Límite superado. Trae el header `Retry-After` (segundos).",
    502: "El proveedor (OpenAI) falló.",
    503: "Función no configurada.",
    504: "El proveedor (OpenAI) tardó demasiado.",
}


def error_responses(*codes: str) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses`` for the given error codes, grouped by HTTP status."""
    responses: dict[int | str, dict[str, Any]] = {}
    for code in codes:
        status, message = ERRORS[code]
        body_code = "invalid_request" if code == "payload_too_large" else code
        entry = responses.setdefault(
            status,
            {
                "model": ErrorResponse,
                "description": DESCRIPTIONS[status],
                "content": {MEDIA_TYPE: {"examples": {}}},
            },
        )
        entry["content"][MEDIA_TYPE]["examples"][code] = {
            "value": {"code": body_code, "message": message}
        }
    return responses


#: Errors every ``/v1`` route can return.
COMMON = ("unauthorized", "invalid_request", "payload_too_large", "rate_limited")


def install_openapi(app: FastAPI) -> None:
    """Generate the schema without FastAPI's automatic 422 "Validation Error".

    This service answers validation errors with ``400 invalid_request`` (documented on
    each route); 422 is only ``not_enough_data`` on the price route.
    """

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            tags=app.openapi_tags,
        )
        for operations in schema.get("paths", {}).values():
            for operation in operations.values():
                responses = operation.get("responses", {})
                default_422 = responses.get("422", {}).get("description") == "Validation Error"
                if default_422:
                    del responses["422"]
        components = schema.get("components", {}).get("schemas", {})
        for name in ("HTTPValidationError", "ValidationError"):
            components.pop(name, None)
        app.openapi_schema = schema
        return schema

    app.openapi = openapi
