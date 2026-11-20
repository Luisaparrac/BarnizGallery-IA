"""Hybrid recommendations with the example catalog index (no OpenAI calls)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import get_settings
from app.main import create_app
from app.recommendations.catalog_index import CatalogIndex
from app.recommendations.recommendation_service import RecommendationService
from app.recommendations.recommendation_weights import RecommendationWeights
from app.schemas.recommendations import RecommendationRequest
from tests.conftest import TEST_API_KEY, build_settings

EXAMPLE = Path(__file__).parent / "data" / "catalog_index_example.json"
NO_DIVERSITY = RecommendationWeights(diversity=0)

# Same content features for every piece, so only what was learned can tell them apart.
BASE = {"colors": ["verde"], "shape": "caja", "style": "tradicional", "motifs": []}
CANDIDATES = [
    {**BASE, "artwork_id": 1, "slug": "bargueno-colonial", "store_id": 1},
    {**BASE, "artwork_id": 2, "slug": "jarron-flora-azul", "store_id": 1},
    {**BASE, "artwork_id": 3, "slug": "jarron-flora-dorada", "store_id": 1},
    {**BASE, "artwork_id": 4, "slug": "mensajero-ancestral", "store_id": 2},
    {**BASE, "artwork_id": 5, "slug": "tradicion", "store_id": 2},
    {**BASE, "artwork_id": 6, "slug": None, "store_id": 3},
]


@pytest.fixture
def catalog() -> CatalogIndex:
    return CatalogIndex.from_file(EXAMPLE)


def recommend(catalog, interactions, weights=NO_DIVERSITY, candidates=CANDIDATES):
    request = RecommendationRequest(candidates=candidates, interactions=interactions, limit=10)
    return RecommendationService(weights, catalog).recommend(request)


def ids(response) -> list[int]:
    return [item.artwork_id for item in response.items]


def test_liking_a_granja_vase_ranks_granja_pieces_first(catalog):
    response = recommend(catalog, [{"artwork_id": 2, "action": "FAVORITE"}])

    assert response.strategy == "hybrid"
    ranking = ids(response)
    assert ranking.index(1) < ranking.index(4)
    assert ranking.index(3) < ranking.index(5)


def test_liking_a_cabrera_stool_ranks_cabrera_pieces_first(catalog):
    ranking = ids(recommend(catalog, [{"artwork_id": 4, "action": "PURCHASE"}]))

    assert ranking.index(5) < ranking.index(1)
    assert ranking.index(5) < ranking.index(2)


def test_without_index_the_ranking_is_the_current_one(catalog):
    interactions = [{"artwork_id": 2, "action": "FAVORITE"}]

    with_index = recommend(catalog, interactions)
    without_index = recommend(None, interactions)

    assert ids(with_index) != ids(without_index)
    assert all(item.reasons.similar_to is None for item in without_index.items)


def test_explains_with_the_liked_work_and_its_master(catalog):
    response = recommend(catalog, [{"artwork_id": 2, "action": "FAVORITE"}])
    bargueno = next(item for item in response.items if item.artwork_id == 1)

    assert bargueno.explanation.startswith(
        "Porque te gustó «Jarrón Flora Azul» de Gilberto Granja."
    )
    assert bargueno.reasons.similar_to == "jarron-flora-azul"


def test_a_work_never_explains_itself(catalog):
    response = recommend(catalog, [{"artwork_id": 2, "action": "FAVORITE"}])
    liked = next(item for item in response.items if item.artwork_id == 2)

    assert "Jarrón Flora Azul" not in liked.explanation
    assert liked.reasons.similar_to is None


def test_master_style_explanation_when_master_affinity_dominates(catalog):
    weights = RecommendationWeights(diversity=0, semantic_weight=0.0, master_weight=0.5)

    response = recommend(catalog, [{"artwork_id": 4, "action": "PURCHASE"}], weights)
    tradicion = next(item for item in response.items if item.artwork_id == 5)

    assert tradicion.explanation.startswith(
        "Del estilo de María Cabrera: retrato indígena y figuras precolombinas."
    )
    assert tradicion.reasons.master_style == "cabrera"


def test_candidates_without_slug_keep_working(catalog):
    response = recommend(catalog, [{"artwork_id": 2, "action": "FAVORITE"}])
    plain = next(item for item in response.items if item.artwork_id == 6)

    assert plain.reasons.similar_to is None
    assert "Porque te gustó" not in plain.explanation


def test_stronger_interactions_weigh_more(catalog):
    # A short view of a Cabrera stool vs. a purchase of a Granja vase: Granja wins.
    interactions = [
        {"artwork_id": 4, "action": "VIEW", "duration_seconds": 3},
        {"artwork_id": 2, "action": "PURCHASE"},
    ]

    ranking = ids(recommend(catalog, interactions))

    assert ranking.index(1) < ranking.index(5)


def test_zero_learned_weights_reproduce_the_content_ranking(catalog):
    weights = RecommendationWeights(diversity=0, semantic_weight=0.0, master_weight=0.0)
    interactions = [{"artwork_id": 2, "action": "FAVORITE"}]

    with_index = recommend(catalog, interactions, weights)
    without_index = recommend(None, interactions, weights)

    assert [i.score for i in with_index.items] == [i.score for i in without_index.items]


def test_diversity_still_applies(catalog):
    response = recommend(
        catalog, [{"artwork_id": 2, "action": "FAVORITE"}], RecommendationWeights(diversity=1.0)
    )

    assert {item.store_id for item in response.items[:3]} == {1, 2, 3}


def test_learned_weights_come_from_settings():
    weights = RecommendationWeights.from_settings(
        build_settings(reco_semantic_weight=0.5, reco_master_weight=0.2)
    )

    assert (weights.semantic_weight, weights.master_weight) == (0.5, 0.2)


def test_learned_weights_cannot_exceed_one():
    with pytest.raises(ValidationError):
        build_settings(reco_semantic_weight=0.8, reco_master_weight=0.3)


def test_endpoint_uses_the_loaded_index(catalog):
    app = create_app(catalog_index=catalog)
    settings = build_settings()
    app.dependency_overrides[get_settings] = lambda: settings
    body = {
        "interactions": [{"artwork_id": 2, "action": "FAVORITE"}],
        "candidates": CANDIDATES,
    }

    response = TestClient(app).post(
        "/v1/recommendations", json=body, headers={"X-API-Key": TEST_API_KEY}
    )

    items = response.json()["items"]
    assert response.status_code == 200
    assert any(item["reasons"]["similar_to"] == "jarron-flora-azul" for item in items)
