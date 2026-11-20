"""Builds data/catalog_index.json: what the AI learns from the museum's real pieces.

Run on a developer's PC (never on Render), with OPENAI_API_KEY in the local .env::

    python scripts/build_catalog_index.py                  # real run (costs a few cents)
    python scripts/build_catalog_index.py --dry-run        # no OpenAI, fake vectors

Steps for each artwork of ``<frontend>/data/obras.csv``:

1. Take its main photo (``public/obras/<master>/<slug>-1.webp``), reduced to 1024 px.
2. Ask a vision model (gpt-6-luna) for a structured description in Spanish: technique,
   colours, figures, style, shape, feeling and 3 to 5 distinctive traits.
3. Turn that description (plus the catalog data) into an embedding with the cheapest
   embedding model (text-embedding-3-small, 256 dimensions).

Then each master's profile is the average of their works' embeddings, with their most
repeated traits. The output has no keys and no photos; it prints what it cost.
"""

import argparse
import base64
import csv
import io
import json
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.text import normalize_code  # noqa: E402
from app.recommendations.catalog_index import CatalogIndexFile  # noqa: E402

VISION_MODEL = "gpt-6-luna"
EMBEDDING_MODEL = "text-embedding-3-small"
DIMENSIONS = 256
MAX_IMAGE_SIDE = 1024
MAX_MASTER_TRAITS = 4
# USD per million tokens (gpt-6-luna input/output, text-embedding-3-small).
PRICE_VISION_INPUT = 0.10
PRICE_VISION_OUTPUT = 0.50
PRICE_EMBEDDING = 0.02

VISION_INSTRUCTIONS = (
    "Eres curador del museo MUSEO de Barniz de Pasto (mopa-mopa), en Pasto, Colombia. "
    "Describe la pieza de la foto para un catálogo. Responde en español, con frases cortas y "
    "en minúscula. En 'rasgos' da de 3 a 5 rasgos visuales distintivos (por ejemplo "
    "'flora densa', 'grecas doradas', 'retrato indígena'), sin repetir la forma."
)
VISION_SCHEMA = {
    "type": "object",
    "properties": {
        "tecnica": {"type": "string"},
        "colores": {"type": "array", "items": {"type": "string"}},
        "figuras": {"type": "array", "items": {"type": "string"}},
        "estilo": {"type": "string"},
        "forma": {"type": "string"},
        "sensacion": {"type": "string"},
        "rasgos": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["tecnica", "colores", "figuras", "estilo", "forma", "sensacion", "rasgos"],
    "additionalProperties": False,
}


@dataclass
class Work:
    slug: str
    master: str
    title_es: str
    title_en: str
    shape: str
    colors: list[str]
    motifs: list[str]
    style: str
    description_es: str
    photo: Path


@dataclass
class Usage:
    vision_input: int = 0
    vision_output: int = 0
    embedding: int = 0
    calls: dict[str, int] = field(default_factory=lambda: {"vision": 0, "embedding": 0})

    @property
    def cost_usd(self) -> float:
        return (
            self.vision_input * PRICE_VISION_INPUT
            + self.vision_output * PRICE_VISION_OUTPUT
            + self.embedding * PRICE_EMBEDDING
        ) / 1_000_000


class Describer(Protocol):
    model: str

    def describe(self, image_b64: str, work: Work, usage: Usage) -> dict[str, Any]: ...


class Embedder(Protocol):
    model: str

    def embed(self, texts: list[str], usage: Usage) -> list[list[float]]: ...


def slugify(text: str) -> str:
    return "-".join(
        part
        for part in "".join(
            char if char.isalnum() else " " for char in normalize_code(text)
        ).split()
    )


def split_codes(value: str) -> list[str]:
    return [code.strip() for code in (value or "").split(",") if code.strip()]


def read_csv(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.open(encoding="utf-8-sig"), delimiter=";"))


def read_works(frontend: Path) -> list[Work]:
    works, missing = [], []
    for row in read_csv(frontend / "data" / "obras.csv"):
        master, slug = row["maestro"].strip(), slugify(row["obra ES"])
        photos = sorted((frontend / "public" / "obras" / master).glob(f"{slug}-1.*"))
        if not photos:
            missing.append(f"{master}/{slug}-1.*")
            continue
        works.append(
            Work(
                slug=slug,
                master=master,
                title_es=row["obra ES"].strip(),
                title_en=row.get("obra EN", "").strip(),
                shape=row.get("forma", "").strip(),
                colors=split_codes(row.get("colores", "")),
                motifs=split_codes(row.get("figuras", "")),
                style=row.get("estilo", "").strip(),
                description_es=row.get("descripción ES", "").strip(),
                photo=photos[0],
            )
        )
    if missing:
        raise SystemExit("Faltan fotos principales: " + ", ".join(missing))
    slugs = [work.slug for work in works]
    if len(slugs) != len(set(slugs)):
        raise SystemExit("Hay obras con el mismo slug")
    return works


def read_masters(frontend: Path) -> dict[str, str]:
    return {
        row["clave"].strip(): row["nombre"].strip()
        for row in read_csv(frontend / "data" / "maestros.csv")
    }


def image_b64(path: Path) -> str:
    """JPEG, at most 1024 px: cheaper and accepted by the vision API."""
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def embedding_text(work: Work, vision: dict[str, Any]) -> str:
    return " ".join(
        [
            f"{work.title_es}.",
            f"Forma: {work.shape}.",
            f"Colores: {', '.join(work.colors)}.",
            f"Figuras: {', '.join(work.motifs)}.",
            f"Estilo: {work.style}.",
            f"Descripción: {work.description_es}",
            f"Técnica: {vision.get('tecnica', '')}.",
            f"Figuras vistas: {', '.join(vision.get('figuras', []))}.",
            f"Sensación: {vision.get('sensacion', '')}.",
            f"Rasgos: {', '.join(vision.get('rasgos', []))}.",
        ]
    )


def top_traits(trait_lists: list[list[str]], limit: int = MAX_MASTER_TRAITS) -> list[str]:
    """Most repeated traits; ties keep the order in which they first appeared."""
    counts: Counter[str] = Counter()
    first_seen: dict[str, int] = {}
    for traits in trait_lists:
        for trait in dict.fromkeys(t.strip().lower() for t in traits if t.strip()):
            counts[trait] += 1
            first_seen.setdefault(trait, len(first_seen))
    return sorted(counts, key=lambda t: (-counts[t], first_seen[t]))[:limit]


def build_index(
    works: list[Work],
    masters: dict[str, str],
    describer: Describer,
    embedder: Embedder,
    usage: Usage,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    unknown = sorted({work.master for work in works} - set(masters))
    if unknown:
        raise SystemExit("Maestros sin fila en maestros.csv: " + ", ".join(unknown))

    visions = []
    for position, work in enumerate(works, start=1):
        log(f"  [{position}/{len(works)}] {work.master}/{work.slug}")
        visions.append(describer.describe(image_b64(work.photo), work, usage))
    vectors = embedder.embed(
        [embedding_text(w, v) for w, v in zip(works, visions, strict=True)], usage
    )

    artworks = {}
    for work, vision, vector in zip(works, visions, vectors, strict=True):
        artworks[work.slug] = {
            "slug": work.slug,
            "master": work.master,
            "title_es": work.title_es,
            "title_en": work.title_en,
            "shape": work.shape,
            "colors": work.colors,
            "motifs": work.motifs,
            "style": work.style,
            "vision": vision,
            "traits": [t.strip().lower() for t in vision.get("rasgos", []) if t.strip()],
            "embedding": [round(float(x), 6) for x in vector],
        }

    profiles = {}
    for master, name in masters.items():
        own = [a for a in artworks.values() if a["master"] == master]
        if not own:
            continue
        mean = np.mean([a["embedding"] for a in own], axis=0)
        profiles[master] = {
            "slug": master,
            "name": name,
            "artworks": [a["slug"] for a in own],
            "traits": top_traits([a["traits"] for a in own]),
            "embedding": [round(float(x), 6) for x in mean],
        }

    index = {
        "version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "vision_model": describer.model,
        "embedding_model": embedder.model,
        "dimensions": len(vectors[0]) if vectors else DIMENSIONS,
        "artworks": artworks,
        "masters": profiles,
    }
    CatalogIndexFile.model_validate(index)  # same validation the service applies
    return index


class OpenAIDescriber:
    model = VISION_MODEL

    def __init__(self, client) -> None:
        self._client = client

    def describe(self, image_b64: str, work: Work, usage: Usage) -> dict[str, Any]:
        response = self._client.responses.create(
            model=self.model,
            instructions=VISION_INSTRUCTIONS,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"Obra: {work.title_es}. Forma del catálogo: {work.shape}.",
                        },
                        {"type": "input_image", "image_url": f"data:image/jpeg;base64,{image_b64}"},
                    ],
                }
            ],
            reasoning={"effort": "low"},
            text={
                "format": {
                    "type": "json_schema",
                    "name": "obra",
                    "schema": VISION_SCHEMA,
                    "strict": True,
                }
            },
            store=False,
        )
        usage.calls["vision"] += 1
        usage.vision_input += response.usage.input_tokens
        usage.vision_output += response.usage.output_tokens
        return json.loads(response.output_text)


class OpenAIEmbedder:
    model = EMBEDDING_MODEL

    def __init__(self, client) -> None:
        self._client = client

    def embed(self, texts: list[str], usage: Usage) -> list[list[float]]:
        response = self._client.embeddings.create(
            model=self.model, input=texts, dimensions=DIMENSIONS
        )
        usage.calls["embedding"] += 1
        usage.embedding += response.usage.total_tokens
        return [item.embedding for item in sorted(response.data, key=lambda d: d.index)]


class FakeDescriber:
    """``--dry-run``: no OpenAI; describes from the catalog data."""

    model = "dry-run"

    def describe(self, image_b64: str, work: Work, usage: Usage) -> dict[str, Any]:
        return {
            "tecnica": "barniz de pasto",
            "colores": work.colors,
            "figuras": work.motifs,
            "estilo": work.style,
            "forma": work.shape,
            "sensacion": "",
            "rasgos": [*work.motifs, work.style],
        }


class FakeEmbedder:
    """``--dry-run``: deterministic vectors from the text (similar text, similar vector)."""

    model = "dry-run"

    def embed(self, texts: list[str], usage: Usage) -> list[list[float]]:
        vectors = []
        for text in texts:
            vector = np.zeros(DIMENSIONS)
            for word in normalize_code(text).split():
                vector[sum(map(ord, word)) % DIMENSIONS] += 1.0
            vectors.append((vector / (np.linalg.norm(vector) or 1)).tolist())
        return vectors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--frontend", type=Path, default=ROOT.parent / "BarnizGallery-Frontend")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "catalog_index.json")
    parser.add_argument("--dry-run", action="store_true", help="sin OpenAI (vectores falsos)")
    args = parser.parse_args(argv)

    works = read_works(args.frontend)
    masters = read_masters(args.frontend)
    usage = Usage()
    if args.dry_run:
        describer, embedder = FakeDescriber(), FakeEmbedder()
    else:
        from openai import OpenAI

        from app.core.config import Settings

        key = Settings(_env_file=ROOT / ".env").openai_api_key.get_secret_value()
        if not key:
            raise SystemExit("Falta OPENAI_API_KEY en el .env")
        client = OpenAI(api_key=key, timeout=120, max_retries=1)
        describer, embedder = OpenAIDescriber(client), OpenAIEmbedder(client)

    print(f"Describiendo {len(works)} obras de {len(masters)} maestros con {describer.model}...")
    index = build_index(works, masters, describer, embedder, usage)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"Índice: {args.out} ({len(index['artworks'])} obras, {len(index['masters'])} maestros)")
    print(
        f"Uso: {usage.calls['vision']} llamadas de visión ({usage.vision_input} tokens de entrada, "
        f"{usage.vision_output} de salida), {usage.calls['embedding']} de embeddings "
        f"({usage.embedding} tokens)."
    )
    print(f"Costo estimado: {usage.cost_usd:.4f} USD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
