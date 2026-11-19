"""JSON responses keep accents and ñ: declared as UTF-8 and encoded as real UTF-8 bytes."""

import json

import pytest

ACCENTED = "Muñeca de Año Nuevo con colibrí"


def assert_utf8_json(response, *expected: str) -> None:
    assert response.headers["content-type"] == "application/json; charset=utf-8"
    raw = response.content
    # Real UTF-8 bytes, never ASCII escapes such as ñ or á.
    assert b"\\u00" not in raw
    for text in expected:
        assert text.encode("utf-8") in raw
    serialized = json.dumps(json.loads(raw.decode("utf-8")), ensure_ascii=False)
    for text in expected:
        assert text in serialized


def test_design_prompt_keeps_accents_and_enye(client, auth_headers):
    body = {
        "request_id": 1,
        "title": ACCENTED,
        "description": "Diseño en señal de cariño",
        "shape": "Bandeja",
        "style": "Tradicional",
        "motifs": ["Colibrí", "Piña"],
    }

    response = client.post("/v1/designs", json=body, headers=auth_headers)

    assert response.status_code == 200
    assert_utf8_json(response, ACCENTED, "Diseño en señal de cariño", "Colibrí", "Piña")


def test_pricing_explanation_keeps_accents(client, auth_headers):
    comparable = {
        "shape": "bandeja",
        "price": 100,
        "currency": "USD",
        "sold": True,
    }
    body = {"piece": {"shape": "bandeja"}, "comparables": [comparable] * 3, "currency": "USD"}

    response = client.post("/v1/pricing/suggest", json=body, headers=auth_headers)

    assert response.status_code == 200
    assert_utf8_json(response, "está", "decides tú")


def test_recommendations_are_utf8_json(client, auth_headers):
    response = client.post("/v1/recommendations", json={}, headers=auth_headers)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json; charset=utf-8"


@pytest.mark.parametrize(
    ("method", "path", "kwargs", "text"),
    [
        ("post", "/v1/designs", {}, "válida"),
        ("post", "/v1/pricing/suggest", {"json": {}, "headers": "auth"}, "válida"),
        ("get", "/no-existe", {}, "método"),
    ],
)
def test_error_messages_keep_accents(client, auth_headers, method, path, kwargs, text):
    if kwargs.get("headers") == "auth":
        kwargs = {**kwargs, "headers": auth_headers}

    response = getattr(client, method)(path, **kwargs)

    assert response.status_code >= 400
    assert_utf8_json(response, text)


def test_health_is_utf8_json(client):
    assert client.get("/health").headers["content-type"] == "application/json; charset=utf-8"
