"""Image provider backed by the OpenAI Images API.

Pattern: **Adapter**. Adapts ``client.images.generate`` (its parameters, its base64
response and its exceptions) to the ``ImageProvider`` interface and to the service's
error codes:

- moderation / safety rejection -> 400 ``content_rejected``
- timeout -> 504 ``provider_timeout``
- any other OpenAI or network failure -> 502 ``provider_error``

The ``OpenAI`` client is injected, so tests use a mock and never call the real API.
"""

import logging

import openai
from openai import OpenAI

from app.core.errors import ErrorCode, ServiceError
from app.designs.image_format import MIME_TYPES, ImageFormat
from app.designs.providers.image_provider import ImageProvider
from app.schemas.designs import DesignRequest, GeneratedImage

logger = logging.getLogger(__name__)

REJECTION_CODES = {"moderation_blocked", "content_policy_violation"}


class OpenAIImageProvider(ImageProvider):
    name = "openai"
    billable = True

    def __init__(
        self,
        client: OpenAI,
        model: str,
        quality: str,
        size: str,
        image_format: ImageFormat = "png",
        compression: int = 80,
    ) -> None:
        self._client = client
        self._model = model
        self._quality = quality
        self._size = size
        self._format = image_format
        self._compression = compression

    @property
    def model(self) -> str:
        return self._model

    def generate(self, prompt: str, request: DesignRequest, count: int) -> list[GeneratedImage]:
        options = {"output_format": self._format}
        if self._format != "png":
            options["output_compression"] = self._compression
        try:
            response = self._client.images.generate(
                model=self._model,
                prompt=prompt,
                n=count,
                quality=self._quality,
                size=self._size,
                **options,
            )
        except openai.APITimeoutError as exc:
            logger.warning("OpenAI image timeout for request %s", request.request_id)
            raise ServiceError(
                ErrorCode.PROVIDER_TIMEOUT,
                "El generador de imágenes tardó demasiado. Inténtalo de nuevo más tarde.",
            ) from exc
        except openai.BadRequestError as exc:
            if self._is_content_rejection(exc):
                logger.info("OpenAI rejected the prompt for request %s", request.request_id)
                raise ServiceError(
                    ErrorCode.CONTENT_REJECTED,
                    "El generador de imágenes rechazó el pedido por su contenido. "
                    "Cambia la descripción e inténtalo de nuevo.",
                ) from exc
            raise self._provider_error(exc, request) from exc
        except openai.OpenAIError as exc:
            raise self._provider_error(exc, request) from exc

        images = [
            GeneratedImage(image_base64=item.b64_json, mime_type=MIME_TYPES[self._format])
            for item in (response.data or [])
            if item.b64_json
        ]
        if not images:
            logger.error("OpenAI returned no images for request %s", request.request_id)
            raise ServiceError(
                ErrorCode.PROVIDER_ERROR, "El generador de imágenes no devolvió ninguna imagen."
            )
        return images

    @staticmethod
    def _is_content_rejection(exc: openai.BadRequestError) -> bool:
        if exc.code in REJECTION_CODES:
            return True
        message = (exc.message or "").lower()
        return "safety system" in message or "moderation" in message

    @staticmethod
    def _provider_error(exc: Exception, request: DesignRequest) -> ServiceError:
        logger.error(
            "OpenAI image error for request %s: %s", request.request_id, type(exc).__name__
        )
        return ServiceError(
            ErrorCode.PROVIDER_ERROR,
            "El generador de imágenes falló. Inténtalo de nuevo más tarde.",
        )
