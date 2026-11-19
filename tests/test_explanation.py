import pytest

from app.recommendations.explanation import explain, spanish_list
from app.schemas.recommendations import Candidate, Reasons

CANDIDATE = Candidate(
    artwork_id=1, colors=["rojo", "verde"], shape="bandeja", style="tradicional", motifs=["colibri"]
)


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        ([], ""),
        (["rojo"], "rojo"),
        (["rojo", "verde"], "rojo y verde"),
        (["a", "b", "c"], "a, b y c"),
    ],
)
def test_spanish_list(items, expected):
    assert spanish_list(items) == expected


def test_full_explanation():
    reasons = Reasons(
        colors=["rojo", "verde"], shape=True, style=True, motifs=["colibri"], budget=True
    )

    assert explain(reasons, CANDIDATE) == (
        "Coincide con lo que te gusta: los colores rojo y verde, la forma bandeja, "
        "el estilo tradicional y la figura colibri. Está dentro de tu presupuesto."
    )


def test_singular_and_out_of_budget():
    reasons = Reasons(colors=["rojo"], budget=False)

    assert explain(reasons, CANDIDATE) == (
        "Coincide con lo que te gusta: el color rojo. "
        "Su precio está por fuera de tu presupuesto."
    )


def test_no_matches():
    assert explain(Reasons(), CANDIDATE) == "Es una obra distinta que puede ampliar tus gustos."
    assert explain(Reasons(), CANDIDATE, popular=True) == (
        "Es una de las obras más populares de la galería."
    )


def test_codes_with_separators_are_readable():
    candidate = Candidate(artwork_id=1, shape="caja_joyero")

    assert "la forma caja joyero" in explain(Reasons(shape=True), candidate)


def test_every_item_has_an_explanation(client, auth_headers):
    body = {
        "profile": {"colors": ["rojo"], "shapes": ["bandeja"]},
        "candidates": [
            {"artwork_id": 1, "colors": ["rojo"], "shape": "bandeja"},
            {"artwork_id": 2, "colors": ["azul"], "shape": "caja"},
        ],
    }

    items = client.post("/v1/recommendations", json=body, headers=auth_headers).json()["items"]

    assert items[0]["explanation"] == (
        "Coincide con lo que te gusta: el color rojo y la forma bandeja."
    )
    assert items[1]["explanation"] == "Es una obra distinta que puede ampliar tus gustos."


def test_popular_strategy_explains_popularity(client, auth_headers):
    body = {"candidates": [{"artwork_id": 1, "popularity": 5}]}

    items = client.post("/v1/recommendations", json=body, headers=auth_headers).json()["items"]

    assert items[0]["explanation"] == "Es una de las obras más populares de la galería."
