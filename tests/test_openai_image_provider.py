"""OpenAI image provider tests. They use a mock client: no real API calls."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx2
import openai
import pytest

from app.api.designs import get_design_service
from app.core.errors import ErrorCode, ServiceError
from app.designs.daily_image_budget import DailyImageBudget
from app.designs.design_service import DesignService
from app.designs.image_provider_factory import ImageProviderFactory
from app.designs.providers.openai_image_provider import OpenAIImageProvider
from app.schemas.designs import DesignRequest
from tests.conftest import build_settings

REQUEST = DesignRequest(request_id=7, title="Caja", shape="Caja", style="Moderno")
API_REQUEST = httpx2.Request("POST", "https://api.openai.com/v1/images/generations")


def make_provider(client: MagicMock) -> OpenAIImageProvider:
    return OpenAIImageProvider(client, model="gpt-image-1-mini", quality="low", size="1024x1024")


def client_returning(*b64_images: str | None) -> MagicMock:
    client = MagicMock()
    data = [SimpleNamespace(b64_json=item) for item in b64_images]
    client.images.generate.return_value = SimpleNamespace(data=data)
    return client


def client_raising(exc: Exception) -> MagicMock:
    client = MagicMock()
    client.images.generate.side_effect = exc
    return client


def status_error(cls: type[openai.APIStatusError], status: int, code: str, message: str):
    response = httpx2.Response(status, request=API_REQUEST)
    return cls(message, response=response, body={"code": code, "message": message})


def assert_service_error(provider: OpenAIImageProvider, code: ErrorCode, status: int) -> None:
    with pytest.raises(ServiceError) as info:
        provider.generate("prompt", REQUEST, 1)
    assert info.value.code == code
    assert info.value.status_code == status


def test_returns_images_and_sends_configuration():
    client = client_returning("aW1hZ2Ux", "aW1hZ2Uy")

    images = make_provider(client).generate("the prompt", REQUEST, 2)

    assert [image.image_base64 for image in images] == ["aW1hZ2Ux", "aW1hZ2Uy"]
    assert all(image.mime_type == "image/png" for image in images)
    client.images.generate.assert_called_once_with(
        model="gpt-image-1-mini",
        prompt="the prompt",
        n=2,
        quality="low",
        size="1024x1024",
        output_format="png",
    )


def test_reports_model_and_name():
    provider = make_provider(MagicMock())

    assert provider.name == "openai"
    assert provider.model == "gpt-image-1-mini"


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("moderation_blocked", "Your request was rejected."),
        ("content_policy_violation", "Rejected."),
        (None, "Your request was rejected as a result of our safety system."),
    ],
)
def test_content_rejection_is_content_rejected(code, message):
    exc = status_error(openai.BadRequestError, 400, code, message)

    assert_service_error(make_provider(client_raising(exc)), ErrorCode.CONTENT_REJECTED, 400)


def test_other_bad_request_is_provider_error():
    exc = status_error(openai.BadRequestError, 400, "invalid_value", "Invalid size.")

    assert_service_error(make_provider(client_raising(exc)), ErrorCode.PROVIDER_ERROR, 502)


def test_timeout_is_provider_timeout():
    exc = openai.APITimeoutError(request=API_REQUEST)

    assert_service_error(make_provider(client_raising(exc)), ErrorCode.PROVIDER_TIMEOUT, 504)


@pytest.mark.parametrize(
    "exc",
    [
        status_error(openai.AuthenticationError, 401, "invalid_api_key", "Bad key."),
        status_error(openai.RateLimitError, 429, "rate_limit_exceeded", "Slow down."),
        status_error(openai.InternalServerError, 500, "server_error", "Oops."),
        openai.APIConnectionError(request=API_REQUEST),
    ],
)
def test_other_failures_are_provider_error(exc):
    assert_service_error(make_provider(client_raising(exc)), ErrorCode.PROVIDER_ERROR, 502)


def test_empty_response_is_provider_error():
    assert_service_error(make_provider(client_returning(None)), ErrorCode.PROVIDER_ERROR, 502)


def test_factory_creates_openai_provider_with_settings():
    settings = build_settings(
        image_provider="openai", openai_api_key="sk-test", openai_image_quality="high"
    )

    provider = ImageProviderFactory.create(settings)

    assert isinstance(provider, OpenAIImageProvider)
    assert provider.model == "gpt-image-2"


def test_endpoint_maps_rejection_to_400(app, client, auth_headers):
    exc = status_error(openai.BadRequestError, 400, "moderation_blocked", "Rejected.")
    provider = make_provider(client_raising(exc))
    app.dependency_overrides[get_design_service] = lambda: DesignService(
        build_settings(), provider, DailyImageBudget()
    )

    response = client.post(
        "/v1/designs",
        json={"request_id": 1, "title": "x", "shape": "Caja", "style": "Moderno"},
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "content_rejected"
