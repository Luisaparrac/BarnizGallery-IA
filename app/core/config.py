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
    moderation_enabled: bool = True
    openai_moderation_model: str = "omni-moderation-latest"

    text_provider: Literal["none", "openai"] = "none"
    openai_text_model: str = ""

    provider_timeout_seconds: float = Field(default=90, gt=0)
    max_images_per_request: int = Field(default=2, ge=1)
    daily_image_limit: int = Field(default=30, ge=0)
    max_request_bytes: int = Field(default=1_000_000, ge=1024)
    rate_limit_per_minute: int = Field(default=20, ge=1)

    #: Set by Render at runtime; shown in /health to know which commit is deployed.
    render_git_commit: str | None = None

    @model_validator(mode="after")
    def _check_provider_requirements(self) -> Self:
        uses_openai = self.image_provider == "openai" or self.text_provider == "openai"
        if uses_openai and not self.openai_api_key.get_secret_value():
            raise ValueError("OPENAI_API_KEY is required when an OpenAI provider is enabled")
        if self.text_provider == "openai" and not self.openai_text_model:
            raise ValueError("OPENAI_TEXT_MODEL is required when TEXT_PROVIDER=openai")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the single, cached ``Settings`` instance."""
    return Settings()
