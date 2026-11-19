"""``GET /v1/metrics``: counters, latency, images of the day and estimated cost."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.openapi_docs import COMMON, error_responses
from app.core.config import Settings, get_settings
from app.schemas.metrics import MetricsResponse

router = APIRouter(tags=["metrics"])


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    summary="Métricas del servicio",
    description=(
        "Contadores por ruta, latencia promedio, imágenes del día y costo estimado de OpenAI "
        "(con los precios configurados). Viven en memoria: se reinician si el servicio se "
        "reinicia o se despierta en Render."
    ),
    responses=error_responses(*COMMON),
)
def metrics(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> MetricsResponse:
    snapshot = request.app.state.metrics.snapshot(
        image_cost_usd=settings.openai_image_cost_usd,
        text_input_usd_per_mtok=settings.openai_text_input_usd_per_mtok,
        text_output_usd_per_mtok=settings.openai_text_output_usd_per_mtok,
    )
    used = request.app.state.image_budget.used_today()
    snapshot["image_budget"] = {
        "daily_image_limit": settings.daily_image_limit,
        "paid_images_used_today": used,
        "remaining_today": max(0, settings.daily_image_limit - used),
    }
    return MetricsResponse(**snapshot)
