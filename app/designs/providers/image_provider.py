"""Common interface for image generation.

Pattern: **Adapter** (target interface). ``DesignService`` only knows ``ImageProvider``;
each concrete provider adapts a different backend (Pillow drawing, OpenAI Images API) to
this single ``generate`` method and to the service's ``GeneratedImage`` model.
"""

from abc import ABC, abstractmethod

from app.schemas.designs import DesignRequest, GeneratedImage


class ImageProvider(ABC):
    #: Value reported in the response's ``provider`` field.
    name: str

    @property
    @abstractmethod
    def model(self) -> str:
        """Model (or engine) name reported in the response."""

    @abstractmethod
    def generate(self, prompt: str, request: DesignRequest, count: int) -> list[GeneratedImage]:
        """Return ``count`` images for the prompt.

        Raises ``ServiceError`` with ``content_rejected``, ``provider_error`` or
        ``provider_timeout`` when the backend fails.
        """
