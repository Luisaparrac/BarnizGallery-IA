"""Ranking quality on a deterministic synthetic catalog (80 pieces, 8 workshops).

These tests measure that the order makes sense, not exact positions: relevance (NDCG),
learning from interactions, budget, diversity, monotonicity and determinism.
"""

import random

from app.recommendations.recommendation_service import RecommendationService
from app.recommendations.recommendation_weights import RecommendationWeights
from app.schemas.recommendations import RecommendationRequest
from tests.synthetic_catalog import catalog, matches, ndcg

CATALOG = catalog()
BY_ID = {item["artwork_id"]: item for item in CATALOG}
TRADITIONAL_RED_TRAYS = {
    "colors": ["rojo"],
    "shapes": ["bandeja"],
    "styles": ["tradicional"],
    "motifs": ["colibri"],
}
NO_DIVERSITY = RecommendationWeights(diversity=0)


def recommend(weights=None, limit=10, candidates=CATALOG, **data):
    service = RecommendationService(weights) if weights else RecommendationService()
    request = RecommendationRequest(candidates=candidates, limit=limit, **data)
    return service.recommend(request)


def test_declared_tastes_rank_the_most_relevant_first():
    for weights in (NO_DIVERSITY, None):
        items = recommend(weights, profile=TRADITIONAL_RED_TRAYS).items
        ranked = [matches(BY_ID[item.artwork_id], TRADITIONAL_RED_TRAYS) for item in items]
        everything = [matches(item, TRADITIONAL_RED_TRAYS) for item in CATALOG]

        assert ndcg(ranked, everything, k=10) >= 0.95


def test_top_results_beat_a_random_order():
    items = recommend(profile=TRADITIONAL_RED_TRAYS).items
    top = sum(matches(BY_ID[item.artwork_id], TRADITIONAL_RED_TRAYS) for item in items) / 10
    average = sum(matches(item, TRADITIONAL_RED_TRAYS) for item in CATALOG) / len(CATALOG)

    assert top >= 2 * average


def test_interactions_steer_the_ranking():
    liked = [
        item["artwork_id"]
        for item in CATALOG
        if item["style"] == "moderno" and "azul" in item["colors"]
    ][:3]
    interactions = [{"artwork_id": artwork_id, "action": "PURCHASE"} for artwork_id in liked]

    response = recommend(interactions=interactions)

    def similar(item: dict) -> bool:
        return item["style"] == "moderno" or "azul" in item["colors"]

    share_top = sum(similar(BY_ID[item.artwork_id]) for item in response.items) / 10
    share_catalog = sum(similar(item) for item in CATALOG) / len(CATALOG)
    assert response.strategy == "hybrid"
    assert share_top >= 0.8
    assert share_top > share_catalog + 0.3


def test_at_equal_similarity_affordable_pieces_come_first():
    profile = {"colors": ["rojo", "azul"], "budget": {"max": 80, "currency": "USD"}}
    items = recommend(NO_DIVERSITY, limit=len(CATALOG), profile=profile).items

    by_relevance: dict[int, list[bool]] = {}
    for item in items:
        artwork = BY_ID[item.artwork_id]
        by_relevance.setdefault(matches(artwork, profile), []).append(artwork["price"] <= 80)

    for affordability in by_relevance.values():
        # Inside each relevance level, every affordable piece precedes every expensive one.
        assert affordability == sorted(affordability, reverse=True)


def test_diversity_spreads_workshops_without_losing_relevance():
    plain = recommend(NO_DIVERSITY, profile=TRADITIONAL_RED_TRAYS).items
    diverse = recommend(profile=TRADITIONAL_RED_TRAYS).items

    def relevance(items):
        return sum(matches(BY_ID[item.artwork_id], TRADITIONAL_RED_TRAYS) for item in items)

    assert len({item.store_id for item in diverse}) >= len({item.store_id for item in plain})
    assert len({item.store_id for item in diverse}) >= 6
    assert relevance(diverse) >= 0.9 * relevance(plain)


def test_adding_a_matching_feature_never_lowers_the_score():
    base = {"artwork_id": 1, "colors": ["verde"], "shape": "caja", "style": "moderno"}
    better = {**base, "artwork_id": 2, "colors": ["verde", "rojo"]}
    best = {**better, "artwork_id": 3, "shape": "bandeja"}

    items = recommend(NO_DIVERSITY, candidates=[base, better, best], profile=TRADITIONAL_RED_TRAYS)
    scores = {item.artwork_id: item.score for item in items.items}

    assert scores[1] <= scores[2] <= scores[3]


def test_order_does_not_depend_on_input_order():
    shuffled = CATALOG[:]
    random.Random(3).shuffle(shuffled)

    original = recommend(profile=TRADITIONAL_RED_TRAYS).items
    reordered = recommend(candidates=shuffled, profile=TRADITIONAL_RED_TRAYS).items

    assert [item.artwork_id for item in original] == [item.artwork_id for item in reordered]
