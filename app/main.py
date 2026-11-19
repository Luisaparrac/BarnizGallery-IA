"""Application entry point: builds the FastAPI app."""

from fastapi import FastAPI

from app import __version__
from app.core.errors import register_error_handlers


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="MUSEO - Servicio de IA",
        description="Diseños, recomendaciones y precio sugerido para el Barniz de Pasto Mopa-Mopa.",
        version=__version__,
    )
    register_error_handlers(app)
    return app


app = create_app()
