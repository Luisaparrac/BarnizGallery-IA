import base64
import io

import pytest
from PIL import Image

from app.designs.design_prompt_builder import DesignPromptBuilder
from app.designs.image_provider_factory import ImageProviderFactory
from app.designs.providers.fake_image_provider import FakeImageProvider
from app.schemas.designs import DesignRequest
from tests.conftest import build_settings

PAYLOAD = {
    "request_id": 42,
    "title": "Bandeja para mi abuela",
    "description": "Bandeja redonda con colibríes y flores",
    "shape": "Bandeja",
    "style": "Tradicional",
    "colors": [{"name": "Rojo", "hex": "#b3261e"}, {"name": "Verde", "hex": "#1E6B3A"}],
    "motifs": ["Colibrí", "Flores"],
    "size_notes": "unos 30 cm",
    "language": "es",
    "count": 1,
}


@pytest.fixture
def design_request() -> DesignRequest:
    return DesignRequest(**PAYLOAD)


# --- DesignPromptBuilder -------------------------------------------------------------


def test_prompt_describes_the_craft_and_the_order(design_request):
    prompt = DesignPromptBuilder.for_request(design_request)

    assert "Barniz de Pasto" in prompt
    assert "resin" in prompt and "wood" in prompt and "glossy" in prompt
    assert '"Bandeja"' in prompt
    assert '"Tradicional"' in prompt
    assert "Rojo (#B3261E)" in prompt
    assert "Colibrí, Flores" in prompt
    assert "unos 30 cm" in prompt
    assert "colibríes y flores" in prompt


def test_prompt_always_has_photo_setup_and_restrictions():
    prompt = DesignPromptBuilder().build()

    assert "cream background" in prompt
    assert "studio lighting" in prompt
    assert "No people" in prompt and "no text" in prompt and "no logos" in prompt


def test_prompt_neutralizes_quotes_and_line_breaks():
    prompt = (
        DesignPromptBuilder()
        .with_customer_notes('Mi "bandeja"', "linea 1\n\nlinea 2", "es")
        .build()
    )

    assert "\n" not in prompt
    assert "Mi 'bandeja' - linea 1 linea 2" in prompt


# --- FakeImageProvider ---------------------------------------------------------------


def test_fake_provider_returns_valid_png(design_request):
    images = FakeImageProvider().generate("prompt", design_request, 1)

    assert len(images) == 1
    assert images[0].mime_type == "image/png"
    image = Image.open(io.BytesIO(base64.b64decode(images[0].image_base64)))
    assert image.format == "PNG"


def test_fake_provider_is_deterministic_and_variants_differ(design_request):
    provider = FakeImageProvider()

    first = provider.generate("prompt", design_request, 2)
    second = provider.generate("prompt", design_request, 2)

    assert first == second
    assert first[0].image_base64 != first[1].image_base64


def test_fake_provider_uses_requested_colors(design_request):
    image_b64 = FakeImageProvider().generate("prompt", design_request, 1)[0].image_base64
    image = Image.open(io.BytesIO(base64.b64decode(image_b64))).convert("RGB")

    colors = {color for _, color in image.getcolors(maxcolors=100_000)}
    assert (0xB3, 0x26, 0x1E) in colors
    assert (0x1E, 0x6B, 0x3A) in colors


def test_fake_provider_works_without_colors():
    request = DesignRequest(**{**PAYLOAD, "colors": [], "motifs": []})

    assert FakeImageProvider().generate("prompt", request, 1)


# --- ImageProviderFactory ------------------------------------------------------------


def test_factory_creates_fake_provider_by_default():
    assert isinstance(ImageProviderFactory.create(build_settings()), FakeImageProvider)


# --- Endpoint ------------------------------------------------------------------------


def test_designs_endpoint_returns_images(client, auth_headers):
    response = client.post("/v1/designs", json=PAYLOAD, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "fake"
    assert body["model"] == "fake-pillow"
    assert "Barniz de Pasto" in body["prompt"]
    assert len(body["images"]) == 1
    assert body["images"][0]["mime_type"] == "image/png"


def test_designs_endpoint_requires_api_key(client):
    response = client.post("/v1/designs", json=PAYLOAD)

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


def test_designs_endpoint_limits_image_count(client, auth_headers):
    response = client.post("/v1/designs", json={**PAYLOAD, "count": 3}, headers=auth_headers)

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_request"
    assert "2" in response.json()["message"]


@pytest.mark.parametrize(
    "change",
    [
        {"title": ""},
        {"shape": None},
        {"count": 0},
        {"colors": [{"name": "Rojo", "hex": "rojo"}]},
    ],
)
def test_designs_endpoint_rejects_invalid_input(client, auth_headers, change):
    response = client.post("/v1/designs", json={**PAYLOAD, **change}, headers=auth_headers)

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_request"
