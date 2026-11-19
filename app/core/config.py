"""Service configuration loaded from environment variables.

Pattern: **Singleton**. ``get_settings`` is wrapped in ``functools.lru_cache``, so the
``Settings`` object is built (and the environment / ``.env`` file read) only once per
process; every caller receives the same instance. Tests replace it through FastAPI's
``dependency_overrides`` instead of touching the real environment.
"""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed view of the environment variables documented in ``.env.example``."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ai_service_key: SecretStr = Field(min_length=1)

    image_provider: Literal["fake", "openai"] = "fake"
    openai_api_key: SecretStr = SecretStr("")
    openai_image_model: str = "gpt-image-2"
    openai_image_quality: Literal["low", "medium", "high"] = "medium"
    openai_image_size: str = "1024x1024"
    #: webp/jpeg weigh much less than png in base64; compression 0-100 (webp/jpeg only).
    openai_image_format: Literal["webp", "jpeg", "png"] = "webp"
    openai_image_compression: int = Field(default=80, ge=0, le=100)
    moderation_enabled: bool = True
    openai_moderation_model: str = "omni-moderation-latest"

    text_provider: Literal["none", "openai"] = "none"
    openai_text_model: str = ""

    provider_timeout_seconds: float = Field(default=90, gt=0)
    max_images_per_request: int = Field(default=2, ge=1)
    daily_image_limit: int = Field(default=30, ge=0)
    max_request_bytes: int = Field(default=1_000_000, ge=1024)
    rate_limit_per_minute: int = Field(default=20, ge=1)

    # Recommendation weights (see RecommendationWeights).
    reco_weight_color: float = Field(default=1.0, ge=0)
    reco_weight_shape: float = Field(default=1.5, ge=0)
    reco_weight_style: float = Field(default=1.2, ge=0)
    reco_weight_motif: float = Field(default=1.3, ge=0)
    reco_budget_share: float = Field(default=0.15, ge=0, le=1)
    reco_profile_share: float = Field(default=0.6, ge=0, le=1)
    reco_diversity: float = Field(default=0.3, ge=0, le=1)

    # Prices used only to *estimate* the cost in /v1/metrics (the OpenAI bill is the truth).
    openai_image_cost_usd: float = Field(default=0.053, ge=0)
    openai_text_input_usd_per_mtok: float = Field(default=0.10, ge=0)
    openai_text_output_usd_per_mtok: float = Field(default=0.50, ge=0)

    #: Set by Render at runtime; shown in /health to know which commit is deployed.
    render_git_commit: str | None = None

    @model_validator(mode="after")
    def _check_provider_requirements(self) -> Self:
        uses_openai = self.image_provider == "openai" or self.text_provider == "openai"
        if uses_openai and not self.openai_api_key.get_secret_value():
            raise ValueError("OPENAI_API_KEY is required when an OpenAI provider is enabled")
        reco_groups = (
            self.reco_weight_color,
            self.reco_weight_shape,
            self.reco_weight_style,
            self.reco_weight_motif,
        )
        if not any(reco_groups):
            raise ValueError("At least one RECO_WEIGHT_* must be greater than 0")
        if self.text_provider == "openai" and not self.openai_text_model:
            raise ValueError("OPENAI_TEXT_MODEL is required when TEXT_PROVIDER=openai")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the single, cached ``Settings`` instance."""
    return Settings()
