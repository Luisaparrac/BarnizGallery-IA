"""Chooses the image provider from the configuration.

Pattern: **Factory Method**. ``create`` hides which concrete ``ImageProvider`` is built
(and how it is configured) behind the ``IMAGE_PROVIDER`` setting, so ``DesignService``
and the routes never import a concrete provider.
"""

from openai import OpenAI

from app.core.config import Settings
from app.core.errors import ErrorCode, ServiceError
from app.designs.providers.fake_image_provider import FakeImageProvider
from app.designs.providers.image_provider import ImageProvider
from app.designs.providers.openai_image_provider import OpenAIImageProvider


class ImageProviderFactory:
    @staticmethod
    def create(settings: Settings) -> ImageProvider:
        match settings.image_provider:
            case "fake":
                return FakeImageProvider()
            case "openai":
                client = OpenAI(
                    api_key=settings.openai_api_key.get_secret_value(),
                    timeout=settings.provider_timeout_seconds,
                    max_retries=0,
                )
                return OpenAIImageProvider(
                    client=client,
                    model=settings.openai_image_model,
                    quality=settings.openai_image_quality,
                    size=settings.openai_image_size,
                )
            case _:
                raise ServiceError(
                    ErrorCode.FEATURE_DISABLED,
                    f"El proveedor de imágenes '{settings.image_provider}' no está disponible.",
                )
