"""Suggested price tests. Text models are fakes or mocks: no real API calls."""

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import httpx2
import openai
import pytest

from app.api.pricing import get_text_model
from app.core.errors import ErrorCode, ServiceError
from app.pricing.comparable_price_estimator import ComparablePriceEstimator, remove_outliers
from app.pricing.llm_price_advisor import LlmPriceAdvisor
from app.pricing.pricing_service import PricingService
from app.pricing.text_models.disabled_text_model import DisabledTextModel
from app.pricing.text_models.openai_text_model import OpenAITextModel
from app.pricing.text_models.text_model import TextModel
from app.schemas.pricing import ComparablePiece, PieceDescription, PricingRequest
from tests.conftest import build_settings

API_REQUEST = httpx2.Request("POST", "https://api.openai.com/v1/responses")
PIECE = {
    "shape": "Bandeja",
    "style": "Tradicional",
    "colors": ["rojo"],
    "motifs": ["Colibrí"],
    "width_cm": 30,
    "height_cm": 30,
    "technique": "barniz",
    "work_hours": 20,
}


def comparable(price: float, sold: bool = False, **changes: Any) -> dict[str, Any]:
    base = {
        "shape": "bandeja",
        "motifs": ["colibri"],
        "width_cm": 30,
        "height_cm": 30,
        "price": price,
        "currency": "USD",
        "sold": sold,
    }
    return {**base, **changes}


SIX = [
    comparable(80, True),
    comparable(95, True),
    comparable(100),
    comparable(115),
    comparable(90, True),
    comparable(120),
]


def make_request(comparables: list[dict[str, Any]] | None = None) -> PricingRequest:
    return PricingRequest(
        piece=PIECE, comparables=SIX if comparables is None else comparables, currency="usd"
    )


class FakeTextModel(TextModel):
    enabled = True

    def __init__(self, answer: dict[str, Any] | Exception) -> None:
        self.answer = answer
        self.calls: list[dict[str, Any]] = []

    def generate_json(self, instructions, prompt, schema_name, schema):
        self.calls.append({"instructions": instructions, "prompt": prompt, "schema": schema})
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def service_with(answer: dict[str, Any] | Exception) -> tuple[PricingService, FakeTextModel]:
    model = FakeTextModel(answer)
    return PricingService(LlmPriceAdvisor(model)), model


# --- ComparablePriceEstimator --------------------------------------------------------


def test_estimator_returns_weighted_median_and_iqr():
    request = make_request()

    estimate = ComparablePriceEstimator().estimate(request.piece, request.comparables, "USD")

    assert estimate.min_price <= estimate.suggested_price <= estimate.max_price
    assert estimate.suggested_price == 95
    assert (estimate.min_price, estimate.max_price) == (90, 115)
    assert estimate.comparables_used == 6
    assert estimate.sold_count == 3


def test_similar_pieces_weigh_more_than_different_ones():
    similar = [comparable(100) for _ in range(3)]
    box = comparable(400, shape="caja", motifs=["geometrico"], width_cm=80)
    different = [box for _ in range(3)]
    request = make_request(similar + different)

    estimate = ComparablePriceEstimator().estimate(request.piece, request.comparables, "USD")

    assert estimate.suggested_price == 100


def test_similarity_is_one_for_identical_piece():
    piece = PieceDescription(**PIECE)

    assert ComparablePriceEstimator.similarity(piece, ComparablePiece(**comparable(1))) == 1.0


def test_comparables_in_other_currency_are_ignored():
    mixed = [*SIX[:2], comparable(300_000, currency="COP"), comparable(400_000, currency="COP")]
    request = make_request(mixed)

    with pytest.raises(ServiceError) as info:
        ComparablePriceEstimator().estimate(request.piece, request.comparables, "USD")

    assert info.value.code == ErrorCode.NOT_ENOUGH_DATA


# --- Text models ---------------------------------------------------------------------


def test_disabled_text_model_is_feature_disabled():
    model = DisabledTextModel()

    assert model.enabled is False
    with pytest.raises(ServiceError) as info:
        model.generate_json("i", "p", "s", {})
    assert info.value.code == ErrorCode.FEATURE_DISABLED


def test_openai_text_model_sends_structured_request():
    client = MagicMock()
    client.responses.create.return_value = SimpleNamespace(
        output_text=json.dumps({"suggested_price": 99, "explanation": "ok"})
    )
    model = OpenAITextModel(client, "gpt-6-luna")

    answer = model.generate_json("instructions", "prompt", "price_advice", {"type": "object"})

    assert answer == {"suggested_price": 99, "explanation": "ok"}
    kwargs = client.responses.create.call_args.kwargs
    assert kwargs["model"] == "gpt-6-luna"
    assert kwargs["instructions"] == "instructions"
    assert kwargs["input"] == "prompt"
    assert kwargs["text"]["format"]["type"] == "json_schema"
    assert kwargs["text"]["format"]["strict"] is True
    assert kwargs["store"] is False


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (openai.APITimeoutError(request=API_REQUEST), ErrorCode.PROVIDER_TIMEOUT),
        (openai.APIConnectionError(request=API_REQUEST), ErrorCode.PROVIDER_ERROR),
        (
            openai.RateLimitError(
                "Slow down.", response=httpx2.Response(429, request=API_REQUEST), body=None
            ),
            ErrorCode.PROVIDER_ERROR,
        ),
    ],
)
def test_openai_text_model_maps_errors(exc, code):
    client = MagicMock()
    client.responses.create.side_effect = exc

    with pytest.raises(ServiceError) as info:
        OpenAITextModel(client, "gpt-6-luna").generate_json("i", "p", "s", {})

    assert info.value.code == code


@pytest.mark.parametrize("output", ["not json", "[1, 2]"])
def test_openai_text_model_rejects_invalid_json(output):
    client = MagicMock()
    client.responses.create.return_value = SimpleNamespace(output_text=output)

    with pytest.raises(ServiceError) as info:
        OpenAITextModel(client, "gpt-6-luna").generate_json("i", "p", "s", {})

    assert info.value.code == ErrorCode.PROVIDER_ERROR


def test_text_model_dependency_follows_settings():
    assert isinstance(get_text_model(build_settings()), DisabledTextModel)
    openai_settings = build_settings(
        text_provider="openai", openai_api_key="sk-test", openai_text_model="gpt-6-luna"
    )
    assert isinstance(get_text_model(openai_settings), OpenAITextModel)


# --- LlmPriceAdvisor -----------------------------------------------------------------


def test_advisor_sends_piece_and_range_and_keeps_price():
    service, model = service_with({"suggested_price": 100, "explanation": "Por las horas."})

    response = service.suggest(make_request())

    assert response.method == "comparables+llm"
    assert response.suggested_price == 100
    assert response.explanation == "Por las horas."
    payload = json.loads(model.calls[0]["prompt"])
    assert payload["piece"]["work_hours"] == 20
    assert payload["range"] == {
        "currency": "USD",
        "min_price": 90,
        "median_price": 95,
        "max_price": 115,
        "comparables_used": 6,
        "sold_count": 3,
    }
    assert "Spanish" in model.calls[0]["instructions"]


@pytest.mark.parametrize(("answer", "expected"), [(500, 115), (1, 90)])
def test_advisor_never_leaves_the_range(answer, expected):
    service, _ = service_with({"suggested_price": answer, "explanation": "x"})

    response = service.suggest(make_request())

    assert response.suggested_price == expected
    assert response.min_price <= response.suggested_price <= response.max_price


# --- PricingService ------------------------------------------------------------------


def test_without_text_model_uses_comparables():
    response = PricingService(LlmPriceAdvisor(DisabledTextModel())).suggest(make_request())

    assert response.method == "comparables"
    assert response.suggested_price == 95
    assert response.currency == "USD"
    assert "6 piezas parecidas" in response.explanation
    assert "sugerencia" in response.explanation


def test_without_text_model_needs_three_comparables():
    service = PricingService(LlmPriceAdvisor(DisabledTextModel()))

    with pytest.raises(ServiceError) as info:
        service.suggest(make_request(SIX[:2]))

    assert info.value.code == ErrorCode.NOT_ENOUGH_DATA
    assert info.value.status_code == 422


@pytest.mark.parametrize("count", [0, 1, 2])
def test_with_text_model_still_needs_three_comparables(count):
    service, model = service_with({"suggested_price": 100, "explanation": "x"})

    with pytest.raises(ServiceError) as info:
        service.suggest(make_request(SIX[:count]))

    assert info.value.code == ErrorCode.NOT_ENOUGH_DATA
    assert model.calls == []


def test_text_model_failure_falls_back_to_comparables():
    error = ServiceError(ErrorCode.PROVIDER_TIMEOUT, "lento")
    service, _ = service_with(error)

    response = service.suggest(make_request())

    assert response.method == "comparables"
    assert response.suggested_price == 95


# --- Endpoint ------------------------------------------------------------------------


def test_endpoint_returns_contract(client, auth_headers):
    body = {"piece": PIECE, "comparables": SIX, "currency": "USD"}

    response = client.post("/v1/pricing/suggest", json=body, headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {
        "suggested_price": 95,
        "min_price": 90,
        "max_price": 115,
        "currency": "USD",
        "method": "comparables",
        "explanation": response.json()["explanation"],
    }


def test_endpoint_not_enough_data_is_422(client, auth_headers):
    body = {"piece": PIECE, "comparables": SIX[:2], "currency": "USD"}

    response = client.post("/v1/pricing/suggest", json=body, headers=auth_headers)

    assert response.status_code == 422
    assert response.json()["code"] == "not_enough_data"


def test_endpoint_uses_text_model_when_enabled(app, client, auth_headers):
    app.dependency_overrides[get_text_model] = lambda: FakeTextModel(
        {"suggested_price": 110, "explanation": "Buen trabajo."}
    )
    body = {"piece": PIECE, "comparables": SIX, "currency": "USD"}

    response = client.post("/v1/pricing/suggest", json=body, headers=auth_headers)

    assert response.json()["method"] == "comparables+llm"
    assert response.json()["suggested_price"] == 110


def test_endpoint_requires_api_key(client):
    assert client.post("/v1/pricing/suggest", json={}).status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {"comparables": SIX, "currency": "USD"},
        {"piece": PIECE, "comparables": SIX, "currency": "dollars"},
        {"piece": {**PIECE, "width_cm": -1}, "comparables": SIX, "currency": "USD"},
        {"piece": PIECE, "comparables": [comparable(0)], "currency": "USD"},
    ],
)
def test_endpoint_rejects_invalid_input(client, auth_headers, body):
    response = client.post("/v1/pricing/suggest", json=body, headers=auth_headers)

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_request"


# --- Outliers (IQR) -------------------------------------------------------------------


def test_outlier_price_is_discarded():
    with_typo = [*SIX, comparable(10_000, True)]  # someone typed 10000 instead of 100

    response = PricingService(LlmPriceAdvisor(DisabledTextModel())).suggest(
        make_request(with_typo)
    )

    assert response.suggested_price == 95
    assert response.max_price <= 120
    assert "Se descartaron 1 precio atípico." in response.explanation
    assert "6 piezas parecidas" in response.explanation


def test_remove_outliers_uses_tukey_fences():
    pieces = [ComparablePiece(**comparable(price)) for price in (90, 95, 100, 105, 110, 400)]

    kept, removed = remove_outliers(pieces, keep_at_least=3)

    assert removed == 1
    assert sorted(item.price for item in kept) == [90, 95, 100, 105, 110]


def test_outliers_are_kept_when_too_few_comparables_remain():
    pieces = [ComparablePiece(**comparable(price)) for price in (100, 100, 100, 900)]

    kept, removed = remove_outliers(pieces, keep_at_least=4)

    assert removed == 0
    assert len(kept) == 4


def test_no_outlier_removal_with_three_comparables():
    pieces = [ComparablePiece(**comparable(price)) for price in (10, 100, 10_000)]

    assert remove_outliers(pieces, keep_at_least=3) == (pieces, 0)


def test_text_model_never_sees_discarded_outliers():
    service, model = service_with({"suggested_price": 100, "explanation": "x"})

    service.suggest(make_request([*SIX, comparable(10_000, True)]))

    payload = json.loads(model.calls[0]["prompt"])
    assert all(item["price"] < 10_000 for item in payload["comparables"])
    assert payload["range"]["comparables_used"] == 6
