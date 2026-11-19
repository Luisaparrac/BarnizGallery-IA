"""Common interface for checking the customer's text.

Pattern: **Adapter** (target interface). ``DesignService`` asks a ``ContentModerator`` to
check the text before spending money on images; ``OpenAIContentModerator`` adapts the
OpenAI moderation endpoint and ``NoopContentModerator`` is used with the free provider.
"""

from abc import ABC, abstractmethod

from app.schemas.designs import DesignRequest

REJECTED_MESSAGE = (
    "El pedido no se puede generar por su contenido. Cambia la descripción e inténtalo de nuevo."
)


def customer_text(request: DesignRequest) -> str:
    """Every piece of free text the customer wrote, joined for a single check."""
    parts = [
        request.title,
        request.description,
        request.shape,
        request.style,
        request.size_notes or "",
        *request.motifs,
        *(color.name for color in request.colors),
    ]
    return "\n".join(part for part in parts if part)


class ContentModerator(ABC):
    @abstractmethod
    def check(self, request: DesignRequest) -> None:
        """Raise ``ServiceError(content_rejected)`` if the text is not allowed."""
