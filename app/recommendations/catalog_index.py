"""What the AI learned from the museum's real pieces: embeddings and master profiles.

``scripts/build_catalog_index.py`` (run on a developer's PC, never on Render) describes each
artwork photo with a vision model, turns the description into an embedding and averages
the embeddings of each master. The result, ``data/catalog_index.json``, is versioned in the
repo and loaded once at startup. Without it the service works exactly as before.

Similarities are cosine similarities between unit vectors, clipped to ``[0, 1]``.
"""

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, Field, ValidationError, model_validator

logger = logging.getLogger(__name__)

#: Spanish labels of the catalog codes, for "what they have in common".
MOTIF_LABELS = {
    "floral": "flora",
    "geometrico": "diseños geométricos",
    "paisaje": "paisaje andino",
    "antropomorfo": "figura humana",
    "precolombino": "diseños precolombinos",
    "zoomorfo": "animales",
    "religioso": "motivos religiosos",
    "abstracto": "formas abstractas",
}
SHAPE_LABELS = {
    "jarron": "jarrón",
    "mascara": "máscara",
    "banco": "banco",
    "plato": "plato",
    "mueble": "mueble",
    "cuadro": "cuadro",
    "escultura": "escultura",
    "bandeja": "bandeja",
    "caja": "caja",
    "cuenco": "cuenco",
    "joyero": "joyero",
    "marco": "marco",
}


class IndexedArtwork(BaseModel):
    slug: str
    master: str
    title_es: str
    title_en: str = ""
    shape: str = ""
    colors: list[str] = Field(default_factory=list)
    motifs: list[str] = Field(default_factory=list)
    style: str = ""
    #: Structured description from the vision model (technique, colours, figures...).
    vision: dict[str, Any] = Field(default_factory=dict)
    #: Short Spanish traits ("flora densa", "grecas doradas").
    traits: list[str] = Field(default_factory=list)
    embedding: list[float]


class IndexedMaster(BaseModel):
    slug: str
    name: str
    artworks: list[str]
    #: Most characteristic Spanish traits of the master's work.
    traits: list[str] = Field(default_factory=list)
    embedding: list[float]


class CatalogIndexFile(BaseModel):
    version: int = 1
    generated_at: str = ""
    vision_model: str = ""
    embedding_model: str = ""
    dimensions: int
    artworks: dict[str, IndexedArtwork]
    masters: dict[str, IndexedMaster]

    @model_validator(mode="after")
    def _check_consistency(self) -> "CatalogIndexFile":
        for item in (*self.artworks.values(), *self.masters.values()):
            if len(item.embedding) != self.dimensions:
                raise ValueError(f"embedding of {item.slug} has the wrong size")
        for artwork in self.artworks.values():
            if artwork.master not in self.masters:
                raise ValueError(f"artwork {artwork.slug} has an unknown master")
        return self


def _unit(values: list[float]) -> np.ndarray:
    vector = np.asarray(values, dtype=float)
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm > 0 else vector


class CatalogIndex:
    def __init__(self, data: CatalogIndexFile) -> None:
        self.data = data
        self._artworks = {slug: _unit(a.embedding) for slug, a in data.artworks.items()}
        self._masters = {slug: _unit(m.embedding) for slug, m in data.masters.items()}

    @classmethod
    def from_file(cls, path: Path) -> "CatalogIndex | None":
        """Load the index; ``None`` (and a warning) if it is missing or invalid."""
        if not path.is_file():
            logger.info("Catalog index not found; recommendations work without it")
            return None
        try:
            data = CatalogIndexFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, ValidationError) as exc:
            logger.warning("Catalog index ignored: invalid file (%s)", type(exc).__name__)
            return None
        logger.info(
            "Catalog index loaded",
            extra={"artworks": len(data.artworks), "masters": len(data.masters)},
        )
        return cls(data)

    def artwork(self, slug: str | None) -> IndexedArtwork | None:
        return self.data.artworks.get(slug) if slug else None

    def master(self, slug: str | None) -> IndexedMaster | None:
        return self.data.masters.get(slug) if slug else None

    def artwork_vector(self, slug: str | None) -> np.ndarray | None:
        return self._artworks.get(slug) if slug else None

    def master_vector(self, slug: str | None) -> np.ndarray | None:
        return self._masters.get(slug) if slug else None

    @staticmethod
    def cosine(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine of two vectors (unit or not), clipped to ``[0, 1]``."""
        norm = float(np.linalg.norm(a) * np.linalg.norm(b))
        return max(0.0, min(1.0, float(a @ b) / norm)) if norm > 0 else 0.0

    def similarity(self, a: str | None, b: str | None) -> float | None:
        """Similarity of two indexed artworks, or ``None`` if one is not indexed."""
        first, second = self.artwork_vector(a), self.artwork_vector(b)
        if first is None or second is None:
            return None
        return self.cosine(first, second)

    def shared_traits(self, a: str, b: str) -> list[str]:
        """What two artworks have in common, in Spanish.

        First the identical traits the vision model wrote for both ("flora densa"), then the
        catalog figures they share ("diseños precolombinos") and the same shape ("forma de
        jarrón"). A label already contained in an earlier one is not repeated.
        """
        first, second = self.artwork(a), self.artwork(b)
        if first is None or second is None:
            return []
        others = {trait.lower() for trait in second.traits}
        shared = [trait for trait in first.traits if trait.lower() in others]
        for motif in first.motifs:
            if motif in second.motifs and motif in MOTIF_LABELS:
                shared.append(MOTIF_LABELS[motif])
        if first.shape and first.shape == second.shape:
            shared.append(f"forma de {SHAPE_LABELS.get(first.shape, first.shape)}")

        unique: list[str] = []
        for label in shared:
            if not any(label.lower() in kept.lower() for kept in unique):
                unique.append(label)
        return unique
