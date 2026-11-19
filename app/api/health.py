"""``GET /health``: public liveness check (no API key)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app import __version__
from app.core.config import Settings, get_settings
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Estado del servicio (sin clave)",
    description="Versión, proveedores activos y commit desplegado en Render.",
)
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(
        version=__version__,
        image_provider=settings.image_provider,
        text_provider=settings.text_provider,
        commit=settings.render_git_commit,
    )
