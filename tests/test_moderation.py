"""Moderation tests with a mock OpenAI client: no real API calls."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx2
import openai
import pytest

from app.api.designs import create_moderator
from app.core.errors import ErrorCode, ServiceError
from app.designs.daily_image_budget import DailyImageBudget
from app.designs.design_service import DesignService
from app.designs.moderation.content_moderator import customer_text
from app.designs.moderation.noop_content_moderator import NoopContentModerator
from app.designs.moderation.openai_content_moderator import OpenAIContentModerator
from app.schemas.designs import DesignRequest
from tests.conftest import build_settings

REQUEST = DesignRequest(
    request_id=3,
    title="Bandeja",
    description="Con colibríes",
    shape="Bandeja",
    style="Tradicional",
    colors=[{"name": "Rojo", "hex": "#B3261E"}],
    motifs=["Colibrí"],
    size_notes="30 cm",
)


def moderation_client(flagged: bool, categories: dict[str, bool] | None = None) -> MagicMock:
    client = MagicMock()
    result = SimpleNamespace(
        flagged=flagged,
        categories=SimpleNamespace(model_dump=lambda: categories or {"violence": flagged}),
    )
    client.moderations.create.return_value = SimpleNamespace(results=[result])
    return client


def test_customer_text_includes_every_free_text_field():
    text = customer_text(REQUEST)

    for part in ("Bandeja", "Con colibríes", "Tradicional", "30 cm", "Colibrí", "Rojo"):
        assert part in text


def test_allowed_text_passes():
    client = moderation_client(flagged=False)

    OpenAIContentModerator(client, "omni-moderation-latest").check(REQUEST)

    client.moderations.create.assert_called_once_with(
        model="omni-moderation-latest", input=customer_text(REQUEST)
    )


def test_flagged_text_is_content_rejected():
    moderator = OpenAIContentModerator(moderation_client(flagged=True), "omni-moderation-latest")

    with pytest.raises(ServiceError) as info:
        moderator.check(REQUEST)

    assert info.value.code == ErrorCode.CONTENT_REJECTED
    assert info.value.status_code == 400


def test_moderation_failure_fails_open():
    client = MagicMock()
    client.moderations.create.side_effect = openai.APITimeoutError(
        request=httpx2.Request("POST", "https://api.openai.com/v1/moderations")
    )

    OpenAIContentModerator(client, "omni-moderation-latest").check(REQUEST)


def test_rejected_text_never_reaches_the_image_provider():
    provider = MagicMock(billable=True)
    budget = DailyImageBudget()
    moderator = OpenAIContentModerator(moderation_client(flagged=True), "omni-moderation-latest")
    service = DesignService(build_settings(), provider, budget, moderator)

    with pytest.raises(ServiceError) as info:
        service.generate(REQUEST)

    assert info.value.code == ErrorCode.CONTENT_REJECTED
    provider.generate.assert_not_called()
    assert budget.used_today() == 0


def test_free_provider_uses_noop_moderator():
    assert isinstance(create_moderator(build_settings()), NoopContentModerator)


def test_openai_provider_uses_openai_moderator():
    settings = build_settings(image_provider="openai", openai_api_key="sk-test")

    assert isinstance(create_moderator(settings), OpenAIContentModerator)


def test_moderation_can_be_disabled():
    settings = build_settings(
        image_provider="openai", openai_api_key="sk-test", moderation_enabled=False
    )

    assert isinstance(create_moderator(settings), NoopContentModerator)
