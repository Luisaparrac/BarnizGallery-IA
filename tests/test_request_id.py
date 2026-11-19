import re

import pytest

from app.core.request_context import resolve_request_id


def test_request_id_is_generated_when_missing(client):
    response = client.get("/health")

    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])


def test_incoming_request_id_is_returned(client):
    response = client.get("/health", headers={"X-Request-ID": "backend-42.abc_1"})

    assert response.headers["X-Request-ID"] == "backend-42.abc_1"


@pytest.mark.parametrize("bad", ["", "x" * 65, "con espacios", "a;b", "<script>"])
def test_malformed_request_id_is_replaced(bad):
    assert resolve_request_id(bad) != bad
    assert re.fullmatch(r"[0-9a-f]{32}", resolve_request_id(bad))


def test_errors_also_carry_the_request_id(client):
    response = client.post("/v1/designs", json={}, headers={"X-Request-ID": "req-1"})

    assert response.status_code == 401
    assert response.headers["X-Request-ID"] == "req-1"


def test_413_carries_the_request_id(make_client, auth_headers):
    client = make_client(max_request_bytes=1024)

    response = client.post(
        "/v1/designs",
        content=b"x" * 2048,
        headers={**auth_headers, "X-Request-ID": "big-1", "Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.headers["X-Request-ID"] == "big-1"
