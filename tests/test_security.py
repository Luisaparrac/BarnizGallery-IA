from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.security import require_api_key
from tests.conftest import TEST_API_KEY, build_settings


@pytest.fixture
def protected_client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    settings = build_settings()
    app.dependency_overrides[get_settings] = lambda: settings

    @app.get("/v1/protected")
    def protected(_: Annotated[None, Depends(require_api_key)]):
        return {"ok": True}

    return TestClient(app)


def test_valid_key_is_accepted(protected_client):
    response = protected_client.get("/v1/protected", headers={"X-API-Key": TEST_API_KEY})

    assert response.status_code == 200


def test_missing_key_is_unauthorized(protected_client):
    response = protected_client.get("/v1/protected")

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


def test_wrong_key_is_unauthorized(protected_client):
    response = protected_client.get("/v1/protected", headers={"X-API-Key": "wrong"})

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"
