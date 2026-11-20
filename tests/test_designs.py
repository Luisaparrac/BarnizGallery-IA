import base64
import io

import numpy as np
import pytest
from PIL import Image

from app.designs.compositions import COMPOSITIONS
from app.designs.design_prompt_builder import MAX_MOTIF_NOTES, DesignPromptBuilder
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
    assert body["images"][0]["mime_type"] == "image/webp"


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


# --- Image format ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("image_format", "pil_format", "mime"),
    [("webp", "WEBP", "image/webp"), ("jpeg", "JPEG", "image/jpeg"), ("png", "PNG", "image/png")],
)
def test_fake_provider_honours_format(design_request, image_format, pil_format, mime):
    image = FakeImageProvider(image_format).generate("prompt", design_request, 1)[0]

    assert image.mime_type == mime
    assert Image.open(io.BytesIO(base64.b64decode(image.image_base64))).format == pil_format


def test_webp_is_much_lighter_than_png_for_photos():
    # Photo-like texture (gradient + seeded noise), like the images OpenAI returns.
    # Flat drawings such as the fake's compress better as PNG, so they are not used here.
    rng = np.random.default_rng(7)
    gradient = np.linspace(0, 255, 512, dtype=np.float32)
    pixels = np.stack([np.add.outer(gradient, gradient) / 2] * 3, axis=-1)
    pixels = np.clip(pixels + rng.normal(0, 12, pixels.shape), 0, 255).astype(np.uint8)
    photo = Image.fromarray(pixels, "RGB")

    webp = FakeImageProvider("webp")._encode(photo)
    png = FakeImageProvider("png")._encode(photo)

    assert len(webp) < len(png) / 2


def test_endpoint_uses_configured_format(make_client, auth_headers):
    client = make_client(openai_image_format="jpeg")

    image = client.post("/v1/designs", json=PAYLOAD, headers=auth_headers).json()["images"][0]

    assert image["mime_type"] == "image/jpeg"
    assert Image.open(io.BytesIO(base64.b64decode(image["image_base64"]))).format == "JPEG"


# --- Variations -----------------------------------------------------------------------


def test_single_image_keeps_default_framing(design_request):
    prompt = DesignPromptBuilder.for_request(design_request)

    assert "Centered product photograph of the whole piece." in prompt
    assert "Composition:" not in prompt


def test_each_image_gets_its_own_composition(make_client, auth_headers):
    client = make_client(max_images_per_request=3)

    body = client.post("/v1/designs", json={**PAYLOAD, "count": 3}, headers=auth_headers).json()

    images = body["images"]
    assert [image["composition"] for image in images] == ["top", "three_quarter", "detail"]
    assert "top-down view" in images[0]["prompt"]
    assert "three-quarter view" in images[1]["prompt"]
    assert "close-up detail of the decorative motifs" in images[2]["prompt"]
    assert len({image["prompt"] for image in images}) == 3
    assert len({image["image_base64"] for image in images}) == 3
    assert body["prompt"] == images[0]["prompt"]


def test_compositions_keep_the_rest_of_the_prompt(design_request):
    for composition in COMPOSITIONS:
        prompt = DesignPromptBuilder.for_request(design_request, composition)
        assert "Barniz de Pasto" in prompt
        assert "No people" in prompt
        assert "Centered product photograph of the whole piece." not in prompt


def test_single_image_has_no_composition(client, auth_headers):
    image = client.post("/v1/designs", json=PAYLOAD, headers=auth_headers).json()["images"][0]

    assert image["composition"] is None
    assert "Barniz de Pasto" in image["prompt"]


# --- Barniz glossary in the prompt -----------------------------------------------------


def glossary_request(**changes) -> DesignRequest:
    base = {
        "request_id": 7,
        "title": "Plato Sol de los Pastos",
        "description": "Plato con el sol de ocho puntas, espirales y grecas",
        "shape": "Plato",
        "style": "Fusión",
        "motifs": ["Precolombino"],
    }
    return DesignRequest(**{**base, **changes})


def test_director_explains_technique_shape_style_and_figures():
    prompt = DesignPromptBuilder.for_request(glossary_request())

    assert "mopa-mopa resin is boiled, kneaded and stretched" in prompt
    assert 'Object: a "Plato" made in this technique: a round turned wooden plate' in prompt
    assert 'Style: "Fusión", fusion style' in prompt
    assert "Sol de los Pastos = the eight-pointed Sun of the Pastos" in prompt
    assert "grecas = stepped Andean fret borders" in prompt


def test_title_identifies_a_bargueno_when_the_shape_is_generic():
    request = glossary_request(
        title="Bargueño para la sala", description="Con flores", shape="Mueble", motifs=[]
    )

    prompt = DesignPromptBuilder.for_request(request)

    assert "colonial bargueño writing cabinet" in prompt
    assert "flora = dense Pasto flora" in prompt


def test_motif_notes_are_capped_and_not_repeated():
    request = glossary_request(
        motifs=["Colibrí", "Jaguar", "Flores", "Precolombino", "Grecas"],
        description="Colibrí, jaguar, toro, guacamaya y paisaje del Galeras",
    )

    prompt = DesignPromptBuilder.for_request(request)
    references = prompt.split("Barniz de Pasto references: ")[1].split(". Customer")[0]

    assert references.count(" = ") == MAX_MOTIF_NOTES
    assert references.count("colibrí = ") == 1
    # The customer's own motifs come before those found in the description.
    assert "toro = " not in references
    assert "Galeras = " not in references


def test_unknown_words_add_no_references():
    request = glossary_request(
        title="Objeto", description="Algo especial", shape="Objeto", style="Libre", motifs=[]
    )

    prompt = DesignPromptBuilder.for_request(request)

    assert "Barniz de Pasto references" not in prompt
    assert 'Object: a "Objeto" made in this technique.' in prompt
    assert 'Style: "Libre".' in prompt


def test_builder_without_glossary_step_keeps_the_plain_prompt():
    prompt = (
        DesignPromptBuilder()
        .with_object("Plato")
        .with_style("Fusión")
        .with_motifs(["Colibrí"])
        .build()
    )

    assert "Technique:" not in prompt
    assert "Barniz de Pasto references" not in prompt
    assert 'Object: a "Plato" made in this technique.' in prompt


def test_glossary_keeps_customer_text_safe():
    request = glossary_request(title='Plato "Sol de los Pastos"\n\nfin')

    prompt = DesignPromptBuilder.for_request(request)

    assert "\n" not in prompt
    assert "Sol de los Pastos = " in prompt


def test_gift_recipient_is_not_painted_as_a_figure():
    # Contract example: "para mi abuela" names who receives it, not a human figure.
    prompt = DesignPromptBuilder.for_request(DesignRequest(**PAYLOAD))

    assert "figura humana" not in prompt
    assert "human figures" not in prompt
    assert "colibrí = stylized hummingbirds" in prompt


def test_requested_portrait_still_adds_human_figures():
    request = DesignRequest(**{**PAYLOAD, "description": "Plato con el retrato de un taita"})

    assert "figura humana = human figures" in DesignPromptBuilder.for_request(request)
