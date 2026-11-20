"""Shared fixtures.

Tests never read the real ``.env`` and never call OpenAI: the settings are built in
memory and injected with ``dependency_overrides``.
"""

from collections.abc import Callable, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app

TEST_API_KEY = "test-service-key"


def build_settings(**overrides) -> Settings:
    return Settings(_env_file=None, ai_service_key=TEST_API_KEY, **overrides)


@pytest.fixture(autouse=True)
def isolate_from_dotenv(tmp_path, monkeypatch):
    """Run every test from an empty folder, so the developer's real ``.env`` is never read.

    ``Settings`` looks for ``.env`` in the current directory; in CI there is none. Without
    this, a test that forgets to inject settings passes locally and fails in CI.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AI_SERVICE_KEY", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    return build_settings()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: settings
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-API-Key": TEST_API_KEY}


@pytest.fixture
def make_client() -> Callable[..., TestClient]:
    """Build a client with custom settings (e.g. ``text_provider="openai"``)."""

    def _make(**overrides) -> TestClient:
        application = create_app()
        custom = build_settings(**overrides)
        application.dependency_overrides[get_settings] = lambda: custom
        return TestClient(application)

    return _make
