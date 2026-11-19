"""Application entry point: builds the FastAPI app."""

from fastapi import Depends, FastAPI

from app import __version__
from app.api import designs, health
from app.core.errors import register_error_handlers
from app.core.security import require_api_key


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="MUSEO - Servicio de IA",
        description="Diseños, recomendaciones y precio sugerido para el Barniz de Pasto Mopa-Mopa.",
        version=__version__,
    )
    register_error_handlers(app)
    app.include_router(health.router)

    protected = {"prefix": "/v1", "dependencies": [Depends(require_api_key)]}
    app.include_router(designs.router, **protected)
    return app


app = create_app()
