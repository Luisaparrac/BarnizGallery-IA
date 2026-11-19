"""Text model used when ``TEXT_PROVIDER=none``.

Pattern: **Adapter** (null object). It fulfils the ``TextModel`` interface without calling
any provider, so callers check ``enabled`` instead of testing for ``None``.
"""

from typing import Any

from app.core.errors import ErrorCode, ServiceError
from app.pricing.text_models.text_model import TextModel


class DisabledTextModel(TextModel):
    enabled = False

    def generate_json(
        self, instructions: str, prompt: str, schema_name: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        raise ServiceError(ErrorCode.FEATURE_DISABLED, "El modelo de texto no está activado.")
