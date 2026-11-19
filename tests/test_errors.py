from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import ErrorCode, ServiceError, register_error_handlers


class Payload(BaseModel):
    title: str


def build_client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    def boom():
        raise ServiceError(ErrorCode.PROVIDER_TIMEOUT, "El proveedor tardó demasiado.")

    @app.post("/echo")
    def echo(payload: Payload):
        return payload

    return TestClient(app)


def test_service_error_uses_common_format():
    response = build_client().get("/boom")

    assert response.status_code == 504
    assert response.json() == {
        "code": "provider_timeout",
        "message": "El proveedor tardó demasiado.",
    }


def test_validation_error_is_invalid_request():
    response = build_client().post("/echo", json={})

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_request"
    assert "title" in response.json()["message"]


def test_unknown_route_uses_common_format():
    response = build_client().get("/does-not-exist")

    assert response.status_code == 404
    assert response.json()["code"] == "invalid_request"
