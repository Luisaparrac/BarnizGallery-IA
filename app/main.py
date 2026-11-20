"""Application entry point: builds the FastAPI app."""

import os
from pathlib import Path

from fastapi import Depends, FastAPI

from app import __version__
from app.api import designs, health, metrics, pricing, recommendations, similar
from app.api.openapi_docs import install_openapi
from app.core.body_limit import BodySizeLimitMiddleware
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging_config import AccessLogMiddleware, setup_logging
from app.core.metrics import MetricsRegistry
from app.core.rate_limiter import SlidingWindowRateLimiter
from app.core.request_context import RequestContextMiddleware
from app.core.responses import Utf8JSONResponse
from app.core.security import enforce_rate_limit, require_api_key
from app.designs.daily_image_budget import DailyImageBudget
from app.recommendations.catalog_index import CatalogIndex


def current_settings(app: FastAPI) -> Settings:
    """Settings as the routes see them (honours ``dependency_overrides`` in tests)."""
    return app.dependency_overrides.get(get_settings, get_settings)()


def env_flag(name: str, default: bool) -> bool:
    """Read a boolean environment variable (``true``/``false``, ``1``/``0``, ``yes``/``no``)."""
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


#: Default location of the catalog index, next to the ``app`` package.
DEFAULT_CATALOG_INDEX = Path(__file__).resolve().parent.parent / "data" / "catalog_index.json"
_LOAD_FROM_ENVIRONMENT = object()


def load_catalog_index() -> CatalogIndex | None:
    """Index path from ``CATALOG_INDEX_PATH`` (read here, like ``LOG_LEVEL``)."""
    return CatalogIndex.from_file(Path(os.getenv("CATALOG_INDEX_PATH") or DEFAULT_CATALOG_INDEX))


def create_app(
    docs_enabled: bool | None = None, catalog_index: object = _LOAD_FROM_ENVIRONMENT
) -> FastAPI:
    """Create the FastAPI application.

    ``DOCS_ENABLED=false`` hides ``/docs``, ``/redoc`` and ``/openapi.json`` (for
    production). It is read from the environment here, like ``LOG_LEVEL``, so creating the
    app never needs ``.env``.
    """
    if docs_enabled is None:
        docs_enabled = env_flag("DOCS_ENABLED", default=True)
    app = FastAPI(
        title="MUSEO - Servicio de IA",
        description="Diseños, recomendaciones y precio sugerido para el Barniz de Pasto Mopa-Mopa.",
        version=__version__,
        default_response_class=Utf8JSONResponse,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        openapi_tags=[
            {"name": "health", "description": "Estado del servicio. No pide clave."},
            {"name": "designs", "description": "Imágenes de propuesta para encargos."},
            {"name": "recommendations", "description": "Obras según los gustos del cliente."},
            {"name": "pricing", "description": "Precio sugerido para el artesano."},
            {"name": "metrics", "description": "Contadores, latencia y costo estimado."},
        ],
    )
    app.state.rate_limiter = SlidingWindowRateLimiter()
    app.state.image_budget = DailyImageBudget()
    app.state.metrics = MetricsRegistry()
    app.state.catalog_index = (
        load_catalog_index() if catalog_index is _LOAD_FROM_ENVIRONMENT else catalog_index
    )
    register_error_handlers(app)
    app.add_middleware(
        BodySizeLimitMiddleware, max_bytes=lambda: current_settings(app).max_request_bytes
    )
    app.add_middleware(AccessLogMiddleware)
    # Added last, so it is the outermost: every log line and even 413 responses carry
    # the X-Request-ID.
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health.router)

    protected = {
        "prefix": "/v1",
        "dependencies": [Depends(enforce_rate_limit), Depends(require_api_key)],
    }
    app.include_router(designs.router, **protected)
    app.include_router(recommendations.router, **protected)
    app.include_router(similar.router, **protected)
    app.include_router(pricing.router, **protected)
    app.include_router(metrics.router, **protected)
    install_openapi(app)
    return app


# LOG_LEVEL is read directly (not through Settings) so importing the app never needs .env.
setup_logging(os.getenv("LOG_LEVEL", "INFO"))
app = create_app()
