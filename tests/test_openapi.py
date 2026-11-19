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
