"""``POST /v1/designs``: design proposals for custom orders."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from openai import OpenAI

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
@router.post("/designs", response_model=DesignResponse)
def create_designs(
    request: DesignRequest,
    service: Annotated[DesignService, Depends(get_design_service)],
) -> DesignResponse:
    return service.generate(request)
