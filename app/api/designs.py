"""``POST /v1/designs``: design proposals for custom orders."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from openai import OpenAI

from app.api.openapi_docs import COMMON, error_responses
from app.core.config import Settings, get_settings
from app.designs.design_service import DesignService
from app.designs.image_provider_factory import ImageProviderFactory
from app.designs.moderation.content_moderator import ContentModerator
from app.designs.moderation.noop_content_moderator import NoopContentModerator
from app.designs.moderation.openai_content_moderator import OpenAIContentModerator
from app.schemas.designs import DesignRequest, DesignResponse

router = APIRouter(tags=["designs"])

#: The moderation check is quick; never wait for it as long as for an image.
MODERATION_TIMEOUT_SECONDS = 10.0


def create_moderator(settings: Settings) -> ContentModerator:
    """Moderate with OpenAI only when images are paid for (provider ``openai``)."""
    if settings.image_provider == "openai" and settings.moderation_enabled:
        client = OpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=min(settings.provider_timeout_seconds, MODERATION_TIMEOUT_SECONDS),
            max_retries=0,
        )
        return OpenAIContentModerator(client, settings.openai_moderation_model)
    return NoopContentModerator()


def get_design_service(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> DesignService:
    return DesignService(
        settings,
        ImageProviderFactory.create(settings),
        request.app.state.image_budget,
        create_moderator(settings),
    )


# Sync route on purpose: providers are blocking, so FastAPI runs it in its thread pool.
@router.post(
    "/designs",
    response_model=DesignResponse,
    summary="Genera propuestas de diseño para un encargo",
    description=(
        "Arma un prompt en inglés (Builder) con la técnica del Barniz de Pasto, la forma, "
        "los colores, las figuras y la descripción del cliente, y genera `count` imágenes.\n\n"
        "- Con `count > 1` cada imagen tiene una composición distinta (`top`, "
        "`three_quarter`, `detail`).\n"
        "- Las imágenes llegan en base64 en el formato configurado (`OPENAI_IMAGE_FORMAT`, "
        "webp por defecto); `mime_type` dice el formato real.\n"
        "- Con OpenAI, el texto del cliente pasa antes por moderación y cuenta para el "
        "límite diario (`DAILY_IMAGE_LIMIT`).\n"
        "- Puede tardar hasta 90 s: usa un timeout de 120 s."
    ),
    responses=error_responses(
        *COMMON, "content_rejected", "budget_exceeded", "provider_error", "provider_timeout"
    ),
)
def create_designs(
    request: DesignRequest,
    service: Annotated[DesignService, Depends(get_design_service)],
) -> DesignResponse:
    return service.generate(request)
