"""Deterministic synthetic catalog and helpers to measure ranking quality."""

import math

import numpy as np

SHAPES = ["bandeja", "caja", "plato", "jarron"]
STYLES = ["tradicional", "moderno", "contemporaneo"]
COLORS = ["rojo", "verde", "amarillo", "azul", "negro", "blanco"]
MOTIFS = ["colibri", "flores", "geometrico", "frailejon", "aves", "hojas"]


def catalog(size: int = 80, stores: int = 8, seed: int = 11) -> list[dict]:
    rng = np.random.default_rng(seed)
    items = []
    for artwork_id in range(1, size + 1):
        items.append(
            {
                "artwork_id": artwork_id,
                "store_id": int(rng.integers(1, stores + 1)),
                "colors": sorted(rng.choice(COLORS, size=2, replace=False).tolist()),
                "shape": str(rng.choice(SHAPES)),
                "style": str(rng.choice(STYLES)),
                "motifs": sorted(rng.choice(MOTIFS, size=2, replace=False).tolist()),
                "price": float(rng.integers(20, 300)),
                "currency": "USD",
                "popularity": float(rng.integers(0, 100)),
            }
        )
    return items


def matches(item: dict, profile: dict) -> int:
    """Ground-truth relevance: how many declared tastes the piece satisfies."""
    return (
        len(set(item["colors"]) & set(profile.get("colors", [])))
        + int(item["shape"] in profile.get("shapes", []))
        + int(item["style"] in profile.get("styles", []))
        + len(set(item["motifs"]) & set(profile.get("motifs", [])))
    )


def ndcg(ranked_relevance: list[float], all_relevance: list[float], k: int) -> float:
    def dcg(values: list[float]) -> float:
        return sum(value / math.log2(position + 2) for position, value in enumerate(values[:k]))

    ideal = dcg(sorted(all_relevance, reverse=True))
    return dcg(ranked_relevance) / ideal if ideal > 0 else 0.0
