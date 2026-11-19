import pytest
from pydantic import ValidationError

from app.core.config import Settings


def make_settings(**overrides) -> Settings:
    return Settings(_env_file=None, ai_service_key="test-key", **overrides)


def test_defaults_use_free_providers():
    settings = make_settings()

    assert settings.image_provider == "fake"
    assert settings.text_provider == "none"
    assert settings.openai_image_model == "gpt-image-2"
    assert settings.max_images_per_request == 2


def test_openai_image_provider_requires_api_key():
    with pytest.raises(ValidationError):
        make_settings(image_provider="openai")


def test_openai_text_provider_requires_model():
    with pytest.raises(ValidationError):
        make_settings(text_provider="openai", openai_api_key="sk-test")


def test_service_key_is_not_exposed_in_repr():
    assert "test-key" not in repr(make_settings())
