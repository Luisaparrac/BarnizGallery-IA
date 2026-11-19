"""Common interface for text generation.

Pattern: **Adapter** (target interface). ``LlmPriceAdvisor`` only knows ``TextModel``;
``OpenAITextModel`` adapts the OpenAI Responses API and ``DisabledTextModel`` stands in
when ``TEXT_PROVIDER=none``.
"""

from abc import ABC, abstractmethod
from typing import Any


class TextModel(ABC):
    #: Whether this model can actually generate text.
    enabled: bool

    @abstractmethod
    def generate_json(
        self, instructions: str, prompt: str, schema_name: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        """Return a JSON object that follows ``schema``.

        Raises ``ServiceError`` (``feature_disabled``, ``provider_error`` or
        ``provider_timeout``) when no answer can be produced.
        """
