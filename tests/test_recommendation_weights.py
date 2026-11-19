import pytest
from pydantic import ValidationError

from app.recommendations.recommendation_service import RecommendationService
from app.recommendations.recommendation_weights import DEFAULT_WEIGHTS, RecommendationWeights
from app.schemas.recommendations import RecommendationRequest
from tests.conftest import build_settings

# Two candidates: one matches the colour, the other the shape.
SAME_COLOR = {"artwork_id": 1, "colors": ["rojo"], "shape": "caja", "popularity": 0}
SAME_SHAPE = {"artwork_id": 2, "colors": ["azul"], "shape": "bandeja", "popularity": 0}
REQUEST = {
    "profile": {"colors": ["rojo"], "shapes": ["bandeja"]},
    "candidates": [SAME_COLOR, SAME_SHAPE],
}


def ranking(weights: RecommendationWeights) -> list[int]:
    response = RecommendationService(weights).recommend(RecommendationRequest(**REQUEST))
    return [item.artwork_id for item in response.items]


def test_defaults_favour_shape_over_colour():
    assert ranking(DEFAULT_WEIGHTS) == [2, 1]


def test_weights_change_the_ranking():
    colour_first = RecommendationWeights(color=3.0, shape=1.0)

    assert ranking(colour_first) == [1, 2]


def test_budget_share_controls_budget_influence():
    request = RecommendationRequest(
        profile={"colors": ["rojo"], "budget": {"max": 100, "currency": "USD"}},
        candidates=[
            {"artwork_id": 1, "colors": ["rojo"], "price": 500, "currency": "USD"},
            {"artwork_id": 2, "colors": ["rojo", "azul"], "price": 50, "currency": "USD"},
        ],
    )

    def first(share: float) -> int:
        weights = RecommendationWeights(budget_share=share)
        return RecommendationService(weights).recommend(request).items[0].artwork_id

    assert first(0.0) == 1  # only similarity: the exact colour match wins
    assert first(0.5) == 2  # the budget matters: the affordable one wins


def test_weights_come_from_settings():
    settings = build_settings(reco_weight_color=2.5, reco_budget_share=0.3, reco_profile_share=0.4)

    weights = RecommendationWeights.from_settings(settings)

    assert weights.color == 2.5
    assert weights.budget_share == 0.3
    assert weights.profile_share == 0.4
    assert weights.shape == DEFAULT_WEIGHTS.shape


def test_all_group_weights_zero_is_invalid():
    with pytest.raises(ValidationError):
        build_settings(
            reco_weight_color=0, reco_weight_shape=0, reco_weight_style=0, reco_weight_motif=0
        )


def test_endpoint_uses_configured_weights(make_client, auth_headers):
    client = make_client(reco_weight_color=3.0, reco_weight_shape=1.0)

    items = client.post("/v1/recommendations", json=REQUEST, headers=auth_headers).json()["items"]

    assert [item["artwork_id"] for item in items] == [1, 2]
