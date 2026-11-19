"""Turns tastes and artworks into comparable vectors.

Each feature is a ``group:code`` pair (``color:rojo``, ``shape:bandeja``,
``style:tradicional``, ``motif:colibri``). The vocabulary is built from the profile and the
candidates of one request and sorted, so results are deterministic. Similarity is a
**weighted cosine**: shape, style and motifs count more than single colours.
"""

from collections.abc import Iterable

import numpy as np

from app.schemas.recommendations import Candidate, Reasons, TasteProfile

GROUP_WEIGHTS = {"color": 1.0, "shape": 1.5, "style": 1.2, "motif": 1.3}


def candidate_features(candidate: Candidate) -> list[str]:
    features = [f"color:{code}" for code in candidate.colors]
    if candidate.shape:
        features.append(f"shape:{candidate.shape}")
    if candidate.style:
        features.append(f"style:{candidate.style}")
    features += [f"motif:{code}" for code in candidate.motifs]
    return features


def profile_features(profile: TasteProfile | None) -> list[str]:
    if profile is None:
        return []
    return (
        [f"color:{code}" for code in profile.colors]
        + [f"shape:{code}" for code in profile.shapes]
        + [f"style:{code}" for code in profile.styles]
        + [f"motif:{code}" for code in profile.motifs]
    )


class FeatureVectorizer:
    def __init__(self, candidates: Iterable[Candidate], profile: TasteProfile | None = None):
        vocabulary = set(profile_features(profile))
        for candidate in candidates:
            vocabulary.update(candidate_features(candidate))
        self._features = sorted(vocabulary)
        self._index = {feature: position for position, feature in enumerate(self._features)}
        self._weights = np.array(
            [GROUP_WEIGHTS[feature.split(":", 1)[0]] for feature in self._features], dtype=float
        )

    @property
    def size(self) -> int:
        return len(self._features)

    def vectorize(self, features: Iterable[str]) -> np.ndarray:
        """Binary vector; features outside the vocabulary are ignored."""
        vector = np.zeros(self.size, dtype=float)
        for feature in features:
            position = self._index.get(feature)
            if position is not None:
                vector[position] = 1.0
        return vector

    def candidate_vector(self, candidate: Candidate) -> np.ndarray:
        return self.vectorize(candidate_features(candidate))

    def profile_vector(self, profile: TasteProfile | None) -> np.ndarray:
        return self.vectorize(profile_features(profile))

    def similarity(self, user: np.ndarray, item: np.ndarray) -> float:
        """Weighted cosine similarity in ``[0, 1]`` (0 when a vector is empty)."""
        dot = float(np.sum(self._weights * user * item))
        norm = float(
            np.sqrt(np.sum(self._weights * user * user) * np.sum(self._weights * item * item))
        )
        return dot / norm if norm > 0 else 0.0

    def matched_reasons(self, user: np.ndarray, candidate: Candidate) -> Reasons:
        """Features of the candidate that the user vector likes (weight > 0)."""

        def liked(feature: str) -> bool:
            position = self._index.get(feature)
            return position is not None and user[position] > 0

        return Reasons(
            colors=[code for code in candidate.colors if liked(f"color:{code}")],
            shape=bool(candidate.shape) and liked(f"shape:{candidate.shape}"),
            style=bool(candidate.style) and liked(f"style:{candidate.style}"),
            motifs=[code for code in candidate.motifs if liked(f"motif:{code}")],
        )
