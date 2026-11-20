import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app, env_flag
from tests.conftest import build_settings

MEDIA = "application/json; charset=utf-8"


def schema(client) -> dict:
    return client.get("/openapi.json").json()


def test_every_route_has_summary_and_description(client):
    for path, operations in schema(client)["paths"].items():
        for operation in operations.values():
            assert operation.get("summary"), path
            assert operation.get("description"), path


def test_request_models_have_examples(client):
    components = schema(client)["components"]["schemas"]

    for name in ("DesignRequest", "RecommendationRequest", "PricingRequest"):
        assert components[name]["examples"], name


def test_errors_are_documented_with_examples(client):
    designs = schema(client)["paths"]["/v1/designs"]["post"]["responses"]

    examples = designs["429"]["content"][MEDIA]["examples"]
    assert set(examples) == {"rate_limited", "budget_exceeded"}
    assert examples["budget_exceeded"]["value"]["code"] == "budget_exceeded"
    assert "$ref" in designs["429"]["content"][MEDIA]["schema"]
    assert set(designs) >= {"200", "400", "401", "413", "429", "502", "504"}


def test_no_misleading_default_422(client):
    document = schema(client)
    paths = document["paths"]

    assert "422" not in paths["/v1/designs"]["post"]["responses"]
    assert "422" not in paths["/v1/recommendations"]["post"]["responses"]
    pricing_422 = paths["/v1/pricing/suggest"]["post"]["responses"]["422"]
    assert "not_enough_data" in pricing_422["content"][MEDIA]["examples"]
    assert "HTTPValidationError" not in document["components"]["schemas"]


def test_docs_page_loads(client):
    assert client.get("/docs").status_code == 200


def test_docs_can_be_disabled():
    client = client_for(create_app(docs_enabled=False))

    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, True),
        ("", True),
        ("true", True),
        ("1", True),
        ("false", False),
        ("0", False),
        ("No", False),
        ("off", False),
    ],
)
def test_docs_enabled_env_flag(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("DOCS_ENABLED", raising=False)
    else:
        monkeypatch.setenv("DOCS_ENABLED", value)

    assert env_flag("DOCS_ENABLED", default=True) is expected


def test_docs_disabled_from_environment(monkeypatch):
    monkeypatch.setenv("DOCS_ENABLED", "false")

    assert client_for(create_app()).get("/docs").status_code == 404


def client_for(app) -> TestClient:
    """Client with test settings injected (never the real configuration)."""
    settings = build_settings()
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)
