"""The catalog index builder with fakes: no OpenAI calls, no real photos."""

import base64
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from PIL import Image

from app.recommendations.catalog_index import CatalogIndex
from scripts import build_catalog_index as builder

OBRAS = (
    "maestro;obra ES;obra EN;fotos;recorte;forma;colores;figuras;estilo;descripción ES\n"
    "granja;Bargueño Colonial;Colonial Bargueño;x;;mueble;blanco, verde;floral, geometrico;"
    "tradicional;Bargueño con flores y grecas.\n"
    "granja;Jarrón Flora Azul;Blue Flora Vase;x;;jarron;azul;floral;contemporaneo;"
    "Jarrón con rosas.\n"
    "cabrera;Tradición;Tradition;x;;banco;naranja;antropomorfo;contemporaneo;Banco con retrato.\n"
)
MAESTROS = (
    "clave;nombre;carpeta\n"
    "granja;Gilberto Granja;Gilberto Granja\n"
    "cabrera;María Cabrera;Maria Cabrera\n"
)


@pytest.fixture
def frontend(tmp_path) -> Path:
    root = tmp_path / "frontend"
    (root / "data").mkdir(parents=True)
    (root / "data" / "obras.csv").write_text(OBRAS, encoding="utf-8-sig")
    (root / "data" / "maestros.csv").write_text(MAESTROS, encoding="utf-8")
    for master, slug in [
        ("granja", "bargueno-colonial"),
        ("granja", "jarron-flora-azul"),
        ("cabrera", "tradicion"),
    ]:
        folder = root / "public" / "obras" / master
        folder.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (2000, 1500), "#B3261E").save(folder / f"{slug}-1.webp")
        Image.new("RGB", (10, 10), "#000000").save(folder / f"{slug}-2.webp")
    return root


class RecordingDescriber(builder.FakeDescriber):
    def __init__(self) -> None:
        self.images: list[str] = []

    def describe(self, image_b64, work, usage):
        self.images.append(image_b64)
        usage.calls["vision"] += 1
        usage.vision_input += 1_000
        usage.vision_output += 200
        result = super().describe(image_b64, work, usage)
        result["rasgos"] = ["flora densa", "grecas"] if work.master == "granja" else ["retrato"]
        return result


class CountingEmbedder(builder.FakeEmbedder):
    def embed(self, texts, usage):
        usage.calls["embedding"] += 1
        usage.embedding += 500
        return super().embed(texts, usage)


def build(frontend):
    usage = builder.Usage()
    describer = RecordingDescriber()
    index = builder.build_index(
        builder.read_works(frontend),
        builder.read_masters(frontend),
        describer,
        CountingEmbedder(),
        usage,
        log=lambda _: None,
    )
    return index, usage, describer


@pytest.mark.parametrize(
    ("title", "slug"),
    [
        ("Bargueño Colonial", "bargueno-colonial"),
        ("Jarrón Flora Dorada Fondo Blanco", "jarron-flora-dorada-fondo-blanco"),
        ("Paisaje típico de Nariño", "paisaje-tipico-de-narino"),
        ("Máscara  Músico", "mascara-musico"),
    ],
)
def test_slugify_matches_the_frontend_files(title, slug):
    assert builder.slugify(title) == slug


def test_reads_works_with_their_main_photo(frontend):
    works = builder.read_works(frontend)

    assert [w.slug for w in works] == ["bargueno-colonial", "jarron-flora-azul", "tradicion"]
    assert works[0].photo.name == "bargueno-colonial-1.webp"
    assert works[0].motifs == ["floral", "geometrico"]


def test_missing_main_photo_stops_the_script(frontend):
    (frontend / "public" / "obras" / "cabrera" / "tradicion-1.webp").unlink()

    with pytest.raises(SystemExit, match="cabrera/tradicion-1"):
        builder.read_works(frontend)


def test_builds_a_valid_index_the_service_can_load(frontend, tmp_path):
    index, _, _ = build(frontend)
    path = tmp_path / "index.json"
    path.write_text(json.dumps(index), encoding="utf-8")

    catalog = CatalogIndex.from_file(path)

    assert catalog is not None
    assert set(catalog.data.artworks) == {"bargueno-colonial", "jarron-flora-azul", "tradicion"}
    assert catalog.artwork("tradicion").master == "cabrera"


def test_master_profile_is_the_average_of_its_works(frontend):
    index, _, _ = build(frontend)
    granja = index["masters"]["granja"]

    works = [index["artworks"][slug]["embedding"] for slug in granja["artworks"]]
    assert granja["artworks"] == ["bargueno-colonial", "jarron-flora-azul"]
    assert granja["embedding"] == pytest.approx(np.mean(works, axis=0).tolist(), abs=1e-6)
    assert granja["traits"] == ["flora densa", "grecas"]
    assert index["masters"]["cabrera"]["name"] == "María Cabrera"


def test_sends_only_reduced_jpeg_main_photos(frontend):
    _, usage, describer = build(frontend)

    assert usage.calls == {"vision": 3, "embedding": 1}
    first = Image.open(io.BytesIO(base64.b64decode(describer.images[0])))
    assert first.format == "JPEG"
    assert max(first.size) == builder.MAX_IMAGE_SIDE


def test_cost_is_computed_from_the_usage(frontend):
    _, usage, _ = build(frontend)

    expected = (3_000 * 0.10 + 600 * 0.50 + 500 * 0.02) / 1_000_000
    assert usage.cost_usd == pytest.approx(expected)


def test_output_has_no_keys_nor_photos(frontend):
    index, _, _ = build(frontend)
    text = json.dumps(index)

    assert "base64" not in text
    assert "sk-" not in text
    assert ".webp" not in text
    assert len(text) < 200_000


def test_unknown_master_stops_the_script(frontend):
    works = builder.read_works(frontend)

    with pytest.raises(SystemExit, match="cabrera"):
        builder.build_index(
            works,
            {"granja": "Gilberto Granja"},
            builder.FakeDescriber(),
            builder.FakeEmbedder(),
            builder.Usage(),
            log=lambda _: None,
        )


def test_dry_run_cli_writes_the_index(frontend, tmp_path, capsys):
    out = tmp_path / "out" / "catalog_index.json"

    assert builder.main(["--frontend", str(frontend), "--out", str(out), "--dry-run"]) == 0

    assert CatalogIndex.from_file(out) is not None
    assert "Costo estimado: 0.0000 USD" in capsys.readouterr().out


def test_real_clients_send_the_expected_requests():
    client = MagicMock()
    client.responses.create.return_value = SimpleNamespace(
        output_text=json.dumps({"rasgos": ["flora densa"]}),
        usage=SimpleNamespace(input_tokens=1200, output_tokens=150),
    )
    client.embeddings.create.return_value = SimpleNamespace(
        data=[
            SimpleNamespace(index=1, embedding=[0.0, 1.0]),
            SimpleNamespace(index=0, embedding=[1.0, 0.0]),
        ],
        usage=SimpleNamespace(total_tokens=40),
    )
    work = builder.Work("s", "m", "T", "", "plato", [], [], "", "", Path("x"))
    usage = builder.Usage()

    vision = builder.OpenAIDescriber(client).describe("QUJD", work, usage)
    vectors = builder.OpenAIEmbedder(client).embed(["a", "b"], usage)

    kwargs = client.responses.create.call_args.kwargs
    assert kwargs["model"] == "gpt-6-luna"
    assert kwargs["text"]["format"]["strict"] is True
    assert kwargs["input"][0]["content"][1]["image_url"] == "data:image/jpeg;base64,QUJD"
    assert client.embeddings.create.call_args.kwargs["model"] == "text-embedding-3-small"
    assert client.embeddings.create.call_args.kwargs["dimensions"] == builder.DIMENSIONS
    assert vision == {"rasgos": ["flora densa"]}
    assert vectors == [[1.0, 0.0], [0.0, 1.0]]  # back in input order
    assert (usage.vision_input, usage.vision_output, usage.embedding) == (1200, 150, 40)
