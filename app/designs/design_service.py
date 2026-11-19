"""Entry point for design generation used by the route.

Pattern: **Facade**. The route only calls ``generate``; the service hides the
``DesignPromptBuilder``, the provider chosen by ``ImageProviderFactory`` and the limits
from the configuration.
"""

from app.core.config import Settings
from app.core.errors import ErrorCode, ServiceError
from app.designs.design_prompt_builder import DesignPromptBuilder
from app.designs.providers.image_provider import ImageProvider
from app.schemas.designs import DesignRequest, DesignResponse


class DesignService:
    def __init__(self, settings: Settings, provider: ImageProvider) -> None:
        self._settings = settings
        self._provider = provider

    def generate(self, request: DesignRequest) -> DesignResponse:
        limit = self._settings.max_images_per_request
        if request.count > limit:
            raise ServiceError(
                ErrorCode.INVALID_REQUEST,
                f"Puedes pedir como máximo {limit} imágenes por llamada.",
            )
        prompt = DesignPromptBuilder.for_request(request)
        images = self._provider.generate(prompt, request, request.count)
        return DesignResponse(
            provider=self._provider.name,
            model=self._provider.model,
            prompt=prompt,
            images=images,
        )
