"""Checks the customer text with OpenAI's moderation endpoint before generating images.

Pattern: **Adapter**. Adapts ``client.moderations.create`` to ``ContentModerator``.
If the text is flagged it raises 400 ``content_rejected`` and no image is paid for.

If the moderation call itself fails (network, timeout, OpenAI error) the request goes on
("fail open"): the image endpoint applies its own moderation and still rejects unsafe
content, so this only skips the early, free check. The failure is logged.
"""

import logging

import openai
from openai import OpenAI

from app.core.errors import ErrorCode, ServiceError
from app.designs.moderation.content_moderator import (
    REJECTED_MESSAGE,
    ContentModerator,
    customer_text,
)
from app.schemas.designs import DesignRequest

logger = logging.getLogger(__name__)


class OpenAIContentModerator(ContentModerator):
    def __init__(self, client: OpenAI, model: str) -> None:
        self._client = client
        self._model = model

    def check(self, request: DesignRequest) -> None:
        try:
            response = self._client.moderations.create(
                model=self._model, input=customer_text(request)
            )
        except openai.OpenAIError as exc:
            logger.warning("Moderation unavailable (%s); continuing", type(exc).__name__)
            return

        flagged = [result for result in response.results if result.flagged]
        if flagged:
            categories = sorted(
                name for name, hit in flagged[0].categories.model_dump().items() if hit
            )
            logger.info("Moderation rejected design request: %s", ",".join(categories))
            raise ServiceError(ErrorCode.CONTENT_REJECTED, REJECTED_MESSAGE)
