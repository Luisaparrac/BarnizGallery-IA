"""Chooses the image provider from the configuration.

Pattern: **Factory Method**. ``create`` hides which concrete ``ImageProvider`` is built
(and how it is configured) behind the ``IMAGE_PROVIDER`` setting, so ``DesignService``
and the routes never import a concrete provider.
"""

from app.core.config import Settings
from app.core.errors import ErrorCode, ServiceError
from app.designs.providers.fake_image_provider import FakeImageProvider
from app.designs.providers.image_provider import ImageProvider


class ImageProviderFactory:
    @staticmethod
    def create(settings: Settings) -> ImageProvider:
        match settings.image_provider:
            case "fake":
                return FakeImageProvider()
            case _:
                raise ServiceError(
                    ErrorCode.FEATURE_DISABLED,
                    f"El proveedor de imágenes '{settings.image_provider}' no está disponible.",
                )
