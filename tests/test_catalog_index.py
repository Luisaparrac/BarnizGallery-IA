import json
from pathlib import Path

import numpy as np
import pytest

from app.main import create_app, load_catalog_index
from app.recommendations.catalog_index import CatalogIndex

EXAMPLE = Path(__file__).parent / "data" / "catalog_index_example.json"


@pytest.fixture
def index() -> CatalogIndex:
    return CatalogIndex.from_file(EXAMPLE)


def test_loads_the_example_index(index):
    assert set(index.data.artworks) == {
        "bargueno-colonial",
        "jarron-flora-azul",
        "jarron-flora-dorada",
        "mensajero-ancestral",
        "tradicion",
    }
    assert index.master("granja").name == "Gilberto Granja"
    assert index.artwork("tradicion").master == "cabrera"


def test_vectors_are_unit_length(index):
    assert np.linalg.norm(index.artwork_vector("jarron-flora-azul")) == pytest.approx(1.0)
    assert np.linalg.norm(index.master_vector("cabrera")) == pytest.approx(1.0)


def test_similarity_reflects_the_pieces(index):
    same_master = index.similarity("bargueno-colonial", "jarron-flora-azul")
    other_master = index.similarity("bargueno-colonial", "mensajero-ancestral")

    assert index.similarity("tradicion", "tradicion") == pytest.approx(1.0)
    assert same_master > 0.9
    assert other_master == 0.0
    assert index.similarity("bargueno-colonial", "no-existe") is None
    assert index.similarity(None, "tradicion") is None


def test_shared_traits(index):
    assert index.shared_traits("jarron-flora-azul", "jarron-flora-dorada") == ["flora densa"]
    assert index.shared_traits("tradicion", "bargueno-colonial") == []


def test_missing_file_returns_none(tmp_path):
    assert CatalogIndex.from_file(tmp_path / "nada.json") is None


@pytest.mark.parametrize(
    "corrupt",
    [
        "no es json",
        json.dumps({"dimensions": 4, "artworks": {}, "masters": {}, "version": "x"}),
        # Wrong embedding size.
        EXAMPLE.read_text(encoding="utf-8").replace('"dimensions": 4', '"dimensions": 5'),
        # Artwork of an unknown master.
        EXAMPLE.read_text(encoding="utf-8").replace('"master": "cabrera"', '"master": "nadie"', 1),
    ],
)
def test_invalid_file_is_ignored(tmp_path, corrupt):
    path = tmp_path / "index.json"
    path.write_text(corrupt, encoding="utf-8")

    assert CatalogIndex.from_file(path) is None


def test_app_loads_the_index_from_the_environment(monkeypatch):
    monkeypatch.setenv("CATALOG_INDEX_PATH", str(EXAMPLE))

    assert load_catalog_index() is not None
    assert create_app().state.catalog_index is not None


def test_app_works_without_index(client):
    assert client.app.state.catalog_index is None
    assert client.get("/health").status_code == 200


def test_index_can_be_injected(index):
    assert create_app(catalog_index=index).state.catalog_index is index
