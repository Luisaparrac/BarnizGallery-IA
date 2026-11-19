"""Entry point for design generation used by the route.

Pattern: **Facade**. The route only calls ``generate``; the service hides the
``DesignPromptBuilder``, the provider chosen by ``ImageProviderFactory`` and the limits
from the configuration: images per request and, for paid providers, the moderation of
the customer text and the daily budget, both checked *before* paying for any image.
"""

from app.core.config import Settings
from app.core.errors import ErrorCode, ServiceError
from app.designs.daily_image_budget import DailyImageBudget
from app.designs.design_prompt_builder import DesignPromptBuilder
from app.designs.moderation.content_moderator import ContentModerator
from app.designs.moderation.noop_content_moderator import NoopContentModerator
from app.designs.providers.image_provider import ImageProvider
from app.schemas.designs import DesignRequest, DesignResponse


class DesignService:
    def __init__(
        self,
        settings: Settings,
        provider: ImageProvider,
        budget: DailyImageBudget,
        moderator: ContentModerator | None = None,
    ) -> None:
        self._settings = settings
        self._provider = provider
        self._budget = budget
        self._moderator = moderator or NoopContentModerator()

    def generate(self, request: DesignRequest) -> DesignResponse:
        limit = self._settings.max_images_per_request
        if request.count > limit:
            raise ServiceError(
                ErrorCode.INVALID_REQUEST,
                f"Puedes pedir como máximo {limit} imágenes por llamada.",
            )
        self._moderator.check(request)
        prompt = DesignPromptBuilder.for_request(request)
        if not self._provider.billable:
            images = self._provider.generate(prompt, request, request.count)
        else:
            self._budget.reserve(request.count, self._settings.daily_image_limit)
            try:
                images = self._provider.generate(prompt, request, request.count)
            except Exception:
                self._budget.release(request.count)
                raise
        return DesignResponse(
            provider=self._provider.name,
            model=self._provider.model,
            prompt=prompt,
            images=images,
        )
