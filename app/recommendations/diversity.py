"""Diversity re-ranking with MMR (Maximal Marginal Relevance) by workshop.

Without it, a workshop with many similar pieces can fill the whole list. MMR picks the
results one at a time, each time choosing the candidate that maximizes::

    (1 - diversity) * relevance - diversity * redundancy

where ``redundancy`` is 1 if a result from the same workshop (``store_id``) was already
chosen and 0 otherwise. ``diversity`` (``RECO_DIVERSITY``) goes from 0 (plain ranking by
relevance) to 1 (one result per workshop first). Items keep their relevance ``score``;
only the order changes. Ties are broken by relevance, popularity and id, so the result is
deterministic.
"""

from dataclasses import dataclass

from app.schemas.recommendations import RecommendationItem


@dataclass(frozen=True)
class Ranked:
    item: RecommendationItem
    popularity: float


def mmr_rerank(entries: list[Ranked], limit: int, diversity: float) -> list[RecommendationItem]:
    def tie_break(entry: Ranked) -> tuple[float, float, int]:
        return (-entry.item.score, -entry.popularity, entry.item.artwork_id)

    remaining = sorted(entries, key=tie_break)
    if diversity <= 0:
        return [entry.item for entry in remaining[:limit]]

    chosen: list[Ranked] = []
    used_stores: set[int] = set()
    while remaining and len(chosen) < limit:

        def marginal(entry: Ranked) -> tuple[float, tuple[float, float, int]]:
            store = entry.item.store_id
            redundancy = 1.0 if store is not None and store in used_stores else 0.0
            value = (1 - diversity) * entry.item.score - diversity * redundancy
            return (-value, tie_break(entry))

        best = min(remaining, key=marginal)
        remaining.remove(best)
        chosen.append(best)
        if best.item.store_id is not None:
            used_stores.add(best.item.store_id)
    return [entry.item for entry in chosen]
