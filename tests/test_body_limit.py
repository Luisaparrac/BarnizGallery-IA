import json

PAYLOAD = {"request_id": 1, "title": "x", "shape": "Bandeja", "style": "Tradicional"}


def test_body_over_the_limit_is_rejected_with_413(make_client, auth_headers):
    client = make_client(max_request_bytes=1024)
    body = {**PAYLOAD, "description": "a" * 2000}

    response = client.post("/v1/designs", json=body, headers=auth_headers)

    assert response.status_code == 413
    assert response.json() == {
        "code": "invalid_request",
        "message": "La solicitud es demasiado grande.",
    }


def test_chunked_body_over_the_limit_is_rejected(make_client, auth_headers):
    client = make_client(max_request_bytes=1024)
    raw = json.dumps({**PAYLOAD, "description": "a" * 2000}).encode()

    def chunks():
        for start in range(0, len(raw), 256):
            yield raw[start : start + 256]

    response = client.post(
        "/v1/designs",
        content=chunks(),
        headers={**auth_headers, "Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["code"] == "invalid_request"


def test_body_under_the_limit_is_accepted(make_client, auth_headers):
    client = make_client(max_request_bytes=4096)

    response = client.post("/v1/designs", json=PAYLOAD, headers=auth_headers)

    assert response.status_code == 200
