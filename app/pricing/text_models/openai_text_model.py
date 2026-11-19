"""Text model backed by the OpenAI Responses API.

Pattern: **Adapter**. Adapts ``client.responses.create`` with structured output
(``json_schema``, strict) to ``TextModel.generate_json`` and maps OpenAI failures to the
service's error codes (timeout -> ``provider_timeout``, anything else ->
``provider_error``). The client is injected, so tests use a mock.
"""

import json
import logging
from typing import Any

import openai
from openai import OpenAI

from app.core.errors import ErrorCode, ServiceError
from app.core.request_context import set_field
from app.pricing.text_models.text_model import TextModel

logger = logging.getLogger(__name__)


class OpenAITextModel(TextModel):
    enabled = True

    def __init__(self, client: OpenAI, model: str) -> None:
        self._client = client
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def generate_json(
        self, instructions: str, prompt: str, schema_name: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        set_field("provider", "openai")
        set_field("model", self._model)
        try:
            response = self._client.responses.create(
                model=self._model,
                instructions=instructions,
                input=prompt,
                reasoning={"effort": "low"},
                text={
                    "format": {
                        "type": "json_schema",
                        "name": schema_name,
                        "schema": schema,
                        "strict": True,
                    }
                },
                store=False,
            )
        except openai.APITimeoutError as exc:
            logger.warning("OpenAI text timeout")
            raise ServiceError(
                ErrorCode.PROVIDER_TIMEOUT, "El modelo de texto tardó demasiado."
            ) from exc
        except openai.OpenAIError as exc:
            logger.error("OpenAI text error: %s", type(exc).__name__)
            raise ServiceError(ErrorCode.PROVIDER_ERROR, "El modelo de texto falló.") from exc

        usage = getattr(response, "usage", None)
        for name in ("input_tokens", "output_tokens"):
            tokens = getattr(usage, name, None)
            if isinstance(tokens, int):
                set_field(name, tokens)

        try:
            data = json.loads(response.output_text)
        except (TypeError, ValueError) as exc:
            logger.error("OpenAI text returned invalid JSON")
            raise ServiceError(
                ErrorCode.PROVIDER_ERROR, "El modelo de texto devolvió una respuesta inválida."
            ) from exc
        if not isinstance(data, dict):
            raise ServiceError(
                ErrorCode.PROVIDER_ERROR, "El modelo de texto devolvió una respuesta inválida."
            )
        return data
