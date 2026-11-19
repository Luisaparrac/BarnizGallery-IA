"""Application entry point: builds the FastAPI app."""

from fastapi import FastAPI

from app import __version__


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    return FastAPI(
        title="MUSEO - Servicio de IA",
        description="Diseños, recomendaciones y precio sugerido para el Barniz de Pasto Mopa-Mopa.",
        version=__version__,
    )


app = create_app()
