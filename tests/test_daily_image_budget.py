from datetime import UTC, datetime, timedelta

import pytest

from app.api.designs import get_design_service
from app.core.errors import ErrorCode, ServiceError
from app.designs.daily_image_budget import DailyImageBudget
from app.designs.design_service import DesignService
from app.designs.providers.fake_image_provider import FakeImageProvider
from app.schemas.designs import DesignRequest
from tests.conftest import build_settings

PAYLOAD = {"request_id": 1, "title": "x", "shape": "Bandeja", "style": "Tradicional"}


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class BillableFakeProvider(FakeImageProvider):
    """Free fake that pretends to cost money, to exercise the budget without OpenAI."""

    billable = True

    def __init__(self, fail: bool = False) -> None:
        super().__init__()
        self.fail = fail

    def generate(self, prompt, request, count, variant=0):
        if self.fail:
            raise ServiceError(ErrorCode.PROVIDER_ERROR, "falló")
        return super().generate(prompt, request, count, variant)


def test_reserve_until_limit_then_budget_exceeded():
    budget = DailyImageBudget()
    budget.reserve(2, limit=3)

    with pytest.raises(ServiceError) as info:
        budget.reserve(2, limit=3)

    assert info.value.code == ErrorCode.BUDGET_EXCEEDED
    assert info.value.status_code == 429
    assert int(info.value.headers["Retry-After"]) > 0
    assert budget.used_today() == 2


def test_counter_resets_at_colombian_midnight():
    # 04:59 UTC is 23:59 in Colombia; one minute later it is a new day there.
    clock = Clock(datetime(2026, 11, 19, 4, 59, tzinfo=UTC))
    budget = DailyImageBudget(clock)
    budget.reserve(3, limit=3)

    clock.now += timedelta(minutes=2)

    assert budget.used_today() == 0
    budget.reserve(3, limit=3)


def test_retry_after_points_to_midnight_in_colombia():
    clock = Clock(datetime(2026, 11, 19, 4, 0, tzinfo=UTC))  # 23:00 in Colombia
    budget = DailyImageBudget(clock)

    with pytest.raises(ServiceError) as info:
        budget.reserve(1, limit=0)

    assert info.value.headers["Retry-After"] == "3600"


def test_release_gives_images_back():
    budget = DailyImageBudget()
    budget.reserve(2, limit=2)
    budget.release(2)

    assert budget.used_today() == 0


def make_service(provider, limit=2, budget=None) -> tuple[DesignService, DailyImageBudget]:
    budget = budget or DailyImageBudget()
    settings = build_settings(daily_image_limit=limit)
    return DesignService(settings, provider, budget), budget


def test_billable_provider_consumes_budget():
    service, budget = make_service(BillableFakeProvider(), limit=2)
    service.generate(DesignRequest(**PAYLOAD))
    service.generate(DesignRequest(**PAYLOAD))

    with pytest.raises(ServiceError) as info:
        service.generate(DesignRequest(**PAYLOAD))

    assert info.value.code == ErrorCode.BUDGET_EXCEEDED
    assert budget.used_today() == 2


def test_failed_generation_does_not_consume_budget():
    service, budget = make_service(BillableFakeProvider(fail=True), limit=2)

    with pytest.raises(ServiceError):
        service.generate(DesignRequest(**PAYLOAD))

    assert budget.used_today() == 0


def test_free_provider_ignores_budget():
    service, budget = make_service(FakeImageProvider(), limit=0)

    assert service.generate(DesignRequest(**PAYLOAD)).images
    assert budget.used_today() == 0


def test_endpoint_returns_429_budget_exceeded(app, client, auth_headers):
    budget = DailyImageBudget()
    settings = build_settings(daily_image_limit=1)
    app.dependency_overrides[get_design_service] = lambda: DesignService(
        settings, BillableFakeProvider(), budget
    )

    first = client.post("/v1/designs", json=PAYLOAD, headers=auth_headers)
    second = client.post("/v1/designs", json=PAYLOAD, headers=auth_headers)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["code"] == "budget_exceeded"
    assert "Retry-After" in second.headers


class FailsOnSecondImage(BillableFakeProvider):
    def generate(self, prompt, request, count, variant=0):
        if variant == 1:
            raise ServiceError(ErrorCode.PROVIDER_TIMEOUT, "lento")
        return super().generate(prompt, request, count, variant)


def test_partial_failure_releases_only_the_missing_images():
    service, budget = make_service(FailsOnSecondImage(), limit=5)

    with pytest.raises(ServiceError) as info:
        service.generate(DesignRequest(**{**PAYLOAD, "count": 2}))

    assert info.value.code == ErrorCode.PROVIDER_TIMEOUT
    assert budget.used_today() == 1  # the first image was generated (and paid for)
