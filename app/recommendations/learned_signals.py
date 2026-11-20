"""Signals learned from the museum's real pieces, for the hybrid strategy.

For one request, ``LearnedSignals`` looks at the works the person viewed, saved or bought
(interactions with candidates that have a ``slug`` in the catalog index) and, for each
candidate, computes:

- **semantic**: how similar it is (visual and semantic embedding) to the liked works,
  weighted by how strong each interaction was (a purchase counts more than a short view);
- **master**: how close the person's taste (weighted average of the liked works) is to the
  profile of the candidate's master.

Candidates without an indexed slug get no signal and keep their usual score.
"""

from dataclasses import dataclass
from typing import Literal

import numpy as np

from app.recommendations.catalog_index import CatalogIndex
from app.schemas.recommendations import Candidate, RecommendationRequest

#: Below these values a signal is too weak to be used as the explanation.
SEMANTIC_EXPLANATION_THRESHOLD = 0.5
MASTER_EXPLANATION_THRESHOLD = 0.5
MAX_TRAITS_IN_EXPLANATION = 2


@dataclass(frozen=True)
class LearnedSignal:
    semantic: float
    master: float
    #: Slug of the liked work this candidate resembles most (``None`` if none).
    similar_to: str | None
    master_slug: str | None
    #: Which signal explains the result: a liked work, the master's style, or neither.
    kind: Literal["similar", "master"] | None = None
    #: Spanish sentence for the explanation, or ``None`` when the signal is weak.
    sentence: str | None = None


class LearnedSignals:
    def __init__(
        self,
        catalog: CatalogIndex,
        request: RecommendationRequest,
        interaction_weight,
        semantic_weight: float,
        master_weight: float,
    ) -> None:
        self._catalog = catalog
        self._semantic_weight = semantic_weight
        self._master_weight = master_weight
        slugs = {c.artwork_id: c.slug for c in request.candidates if catalog.artwork(c.slug)}

        liked: dict[str, float] = {}
        for interaction in request.interactions:
            slug = slugs.get(interaction.artwork_id)
            if slug:
                liked[slug] = liked.get(slug, 0.0) + interaction_weight(interaction)
        peak = max(liked.values(), default=0.0)
        #: Liked works with their strength normalized to ``(0, 1]``.
        self.liked = {slug: weight / peak for slug, weight in liked.items()} if peak else {}

        self._taste: np.ndarray | None = None
        if self.liked:
            taste = sum(
                weight * catalog.artwork_vector(slug) for slug, weight in self.liked.items()
            )
            self._taste = taste

    def signal(self, candidate: Candidate) -> LearnedSignal | None:
        artwork = self._catalog.artwork(candidate.slug)
        if artwork is None or not self.liked:
            return None

        semantic, similar_to = 0.0, None
        for slug, strength in self.liked.items():
            if slug == candidate.slug:
                continue  # "because you liked X" never points to X itself
            value = (self._catalog.similarity(candidate.slug, slug) or 0.0) * strength
            if value > semantic:
                semantic, similar_to = value, slug

        master_vector = self._catalog.master_vector(artwork.master)
        master = 0.0
        if master_vector is not None and self._taste is not None:
            master = CatalogIndex.cosine(self._taste, master_vector)

        kind, sentence = self._explanation(semantic, similar_to, master, artwork.master)
        return LearnedSignal(
            semantic=semantic,
            master=master,
            similar_to=similar_to,
            master_slug=artwork.master,
            kind=kind,
            sentence=sentence,
        )

    def _explanation(
        self, semantic: float, similar_to: str | None, master: float, master_slug: str
    ) -> tuple[Literal["similar", "master"] | None, str | None]:
        semantic_wins = semantic * self._semantic_weight >= master * self._master_weight
        if similar_to and semantic >= SEMANTIC_EXPLANATION_THRESHOLD and semantic_wins:
            liked = self._catalog.artwork(similar_to)
            liked_master = self._catalog.master(liked.master)
            return "similar", f"Porque te gustó «{liked.title_es}» de {liked_master.name}."
        profile = self._catalog.master(master_slug)
        if profile and master >= MASTER_EXPLANATION_THRESHOLD and self._master_weight > 0:
            traits = profile.traits[:MAX_TRAITS_IN_EXPLANATION]
            detail = f": {' y '.join(traits)}" if traits else ""
            return "master", f"Del estilo de {profile.name}{detail}."
        return None, None
