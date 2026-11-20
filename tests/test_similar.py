"""POST /v1/similar with the example catalog index (no OpenAI calls)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.recommendations.catalog_index import CatalogIndex
from tests.conftest import TEST_API_KEY, build_settings

EXAMPLE = Path(__file__).parent / "data" / "catalog_index_example.json"
HEADERS = {"X-API-Key": TEST_API_KEY}
CANDIDATES = [
    {"artwork_id": 1, "slug": "bargueno-colonial", "store_id": 1},
    {"artwork_id": 3, "slug": "jarron-flora-dorada", "store_id": 1},
    {"artwork_id": 4, "slug": "mensajero-ancestral", "store_id": 2},
    {"artwork_id": 5, "slug": "tradicion", "store_id": 2},
    {"artwork_id": 9, "slug": "no-indexada", "store_id": 3},
]


def client_with(catalog) -> TestClient:
    app = create_app(catalog_index=catalog)
    settings = build_settings()
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


@pytest.fixture
def client() -> TestClient:
    return client_with(CatalogIndex.from_file(EXAMPLE))


def similar(client, slug="jarron-flora-azul", candidates=CANDIDATES, **extra):
    body = {"artwork": {"artwork_id": 2, "slug": slug}, "candidates": candidates, **extra}
    return client.post("/v1/similar", json=body, headers=HEADERS)


def test_most_similar_first_with_reasons(client):
    response = similar(client)

    assert response.status_code == 200
    body = response.json()
    assert (body["artwork_id"], body["slug"]) == (2, "jarron-flora-azul")
    items = body["items"]
    # Example vectors: golden vase 0.974, bargueño 0.949, Cabrera's stools far behind.
    assert [item["slug"] for item in items][:2] == ["jarron-flora-dorada", "bargueno-colonial"]
    first = items[0]
    assert first["same_master"] is True
    assert first["shared_traits"] == ["flora densa", "forma de jarrón"]
    assert first["explanation"] == (
        "Comparte con «Jarrón Flora Azul»: flora densa y forma de jarrón. "
        "También es de Gilberto Granja."
    )
    assert 0 <= items[-1]["score"] <= first["score"] <= 1


def test_explanation_without_shared_traits(client):
    items = similar(client).json()["items"]
    stool = next(item for item in items if item["slug"] == "tradicion")

    assert stool["same_master"] is False
    assert stool["explanation"] == (
        "Se parece a «Jarrón Flora Azul» en su técnica, colores y figuras."
    )


def test_skips_unindexed_and_the_artwork_itself(client):
    candidates = [*CANDIDATES, {"artwork_id": 2, "slug": "jarron-flora-azul"}]

    slugs = [item["slug"] for item in similar(client, candidates=candidates).json()["items"]]

    assert "no-indexada" not in slugs
    assert "jarron-flora-azul" not in slugs
    assert len(slugs) == 4


def test_respects_limit(client):
    assert len(similar(client, limit=2).json()["items"]) == 2


def test_unknown_artwork_is_not_enough_data(client):
    response = similar(client, slug="no-existe")

    assert response.status_code == 422
    assert response.json()["code"] == "not_enough_data"


def test_without_index_is_feature_disabled():
    response = similar(client_with(None))

    assert response.status_code == 503
    assert response.json()["code"] == "feature_disabled"


def test_requires_api_key(client):
    response = client.post("/v1/similar", json={})

    assert response.status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {"candidates": []},
        {"artwork": {"artwork_id": 1, "slug": "Con Mayúsculas"}},
        {"artwork": {"artwork_id": 1, "slug": "ok"}, "limit": 0},
    ],
)
def test_invalid_input(client, body):
    response = client.post("/v1/similar", json=body, headers=HEADERS)

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_request"


def test_is_documented_in_openapi(client):
    operation = client.get("/openapi.json").json()["paths"]["/v1/similar"]["post"]

    assert operation["summary"] == "Obras parecidas a una obra"
    assert {"401", "422", "503"} <= set(operation["responses"])
