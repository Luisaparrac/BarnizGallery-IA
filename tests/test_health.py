def test_health_is_public_and_reports_providers(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": "1.1.0",
        "image_provider": "fake",
        "text_provider": "none",
        "commit": None,
    }


def test_health_reports_deployed_commit(make_client):
    client = make_client(render_git_commit="abc123")

    assert client.get("/health").json()["commit"] == "abc123"


def test_health_reports_openai_providers(make_client):
    client = make_client(
        image_provider="openai",
        text_provider="openai",
        openai_api_key="sk-test",
        openai_text_model="gpt-6-luna",
    )

    body = client.get("/health").json()

    assert body["image_provider"] == "openai"
    assert body["text_provider"] == "openai"
