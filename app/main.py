"""Application entry point: builds the FastAPI app."""

from fastapi import Depends, FastAPI

from app import __version__
from app.api import designs, health, pricing, recommendations
from app.core.body_limit import BodySizeLimitMiddleware
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.rate_limiter import SlidingWindowRateLimiter
from app.core.responses import Utf8JSONResponse
from app.core.security import enforce_rate_limit, require_api_key
from app.designs.daily_image_budget import DailyImageBudget


def current_settings(app: FastAPI) -> Settings:
    """Settings as the routes see them (honours ``dependency_overrides`` in tests)."""
    return app.dependency_overrides.get(get_settings, get_settings)()


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="MUSEO - Servicio de IA",
        description="Diseños, recomendaciones y precio sugerido para el Barniz de Pasto Mopa-Mopa.",
        version=__version__,
        default_response_class=Utf8JSONResponse,
    )
    app.state.rate_limiter = SlidingWindowRateLimiter()
    app.state.image_budget = DailyImageBudget()
    register_error_handlers(app)
    app.add_middleware(
        BodySizeLimitMiddleware, max_bytes=lambda: current_settings(app).max_request_bytes
    )
    app.include_router(health.router)

    protected = {
        "prefix": "/v1",
        "dependencies": [Depends(enforce_rate_limit), Depends(require_api_key)],
    }
    app.include_router(designs.router, **protected)
    app.include_router(recommendations.router, **protected)
    app.include_router(pricing.router, **protected)
    return app


app = create_app()
