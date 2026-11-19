"""Entry point for design generation used by the route.

Pattern: **Facade**. The route only calls ``generate``; the service hides the
``DesignPromptBuilder``, the provider chosen by ``ImageProviderFactory`` and the limits
from the configuration: images per request and, for paid providers, the moderation of
the customer text and the daily budget, both checked *before* paying for any image.

With ``count > 1`` every image gets its own composition (top view, three-quarter view,
detail of the motifs) and therefore its own prompt. The images are requested in parallel,
so asking for two does not double the waiting time.
"""

from concurrent.futures import ThreadPoolExecutor

from app.core.config import Settings
from app.core.errors import ErrorCode, ServiceError
from app.designs.compositions import Composition, compositions_for
from app.designs.daily_image_budget import DailyImageBudget
from app.designs.design_prompt_builder import DesignPromptBuilder
from app.designs.moderation.content_moderator import ContentModerator
from app.designs.moderation.noop_content_moderator import NoopContentModerator
from app.designs.providers.image_provider import ImageProvider
from app.schemas.designs import DesignRequest, DesignResponse, GeneratedImage


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

        compositions = compositions_for(request.count)
        prompts = [DesignPromptBuilder.for_request(request, item) for item in compositions]

        if self._provider.billable:
            self._budget.reserve(len(prompts), self._settings.daily_image_limit)
        images = self._render_all(request, compositions, prompts)

        return DesignResponse(
            provider=self._provider.name,
            model=self._provider.model,
            prompt=prompts[0],
            images=images,
        )

    def _render_all(
        self,
        request: DesignRequest,
        compositions: list[Composition | None],
        prompts: list[str],
    ) -> list[GeneratedImage]:
        def render(position: int) -> GeneratedImage:
            image = self._provider.generate(prompts[position], request, 1, variant=position)[0]
            composition = compositions[position]
            return image.model_copy(
                update={
                    "composition": composition.code if composition else None,
                    "prompt": prompts[position],
                }
            )

        if len(prompts) == 1:
            outcomes = [self._attempt(render, 0)]
        else:
            with ThreadPoolExecutor(max_workers=len(prompts)) as pool:
                outcomes = list(
                    pool.map(lambda position: self._attempt(render, position), range(len(prompts)))
                )

        failures = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
        if failures:
            if self._provider.billable:
                # Only the images that were not generated go back to the daily budget.
                self._budget.release(len(failures))
            raise failures[0]
        return outcomes

    @staticmethod
    def _attempt(render, position: int) -> GeneratedImage | Exception:
        try:
            return render(position)
        except Exception as exc:
            # Returned, not raised: the caller releases the budget and then re-raises it.
            return exc
