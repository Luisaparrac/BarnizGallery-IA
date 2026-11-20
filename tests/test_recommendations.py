import pytest

from app.recommendations.budget import budget_fit
from app.recommendations.feature_vectorizer import FeatureVectorizer
from app.recommendations.recommendation_service import RecommendationService
from app.recommendations.recommendation_weights import RecommendationWeights
from app.recommendations.strategies.content_based_strategy import ContentBasedStrategy
from app.recommendations.strategies.hybrid_strategy import HybridStrategy, interaction_weight
from app.recommendations.strategies.popularity_strategy import PopularityStrategy
from app.schemas.recommendations import (
    Budget,
    Candidate,
    Interaction,
    RecommendationRequest,
    TasteProfile,
)
from tests.conftest import build_settings

TRAY = {
    "artwork_id": 5,
    "store_id": 2,
    "colors": ["rojo", "amarillo"],
    "shape": "bandeja",
    "style": "tradicional",
    "motifs": ["colibri"],
    "price": 80,
    "currency": "USD",
    "popularity": 12,
}
BOX = {
    "artwork_id": 6,
    "store_id": 3,
    "colors": ["azul"],
    "shape": "caja",
    "style": "moderno",
    "motifs": ["geometrico"],
    "price": 300,
    "currency": "USD",
    "popularity": 50,
}
PLATE = {
    "artwork_id": 7,
    "store_id": 2,
    "colors": ["azul", "verde"],
    "shape": "bandeja",
    "style": "moderno",
    "motifs": ["flores"],
    "price": 60,
    "currency": "USD",
    "popularity": 1,
}
NO_DIVERSITY = RecommendationWeights(diversity=0)

PROFILE = {
    "colors": ["rojo"],
    "shapes": ["bandeja"],
    "styles": ["tradicional"],
    "motifs": ["colibri"],
    "budget": {"min": 20, "max": 120, "currency": "USD"},
}


def make_request(**data) -> RecommendationRequest:
    data.setdefault("candidates", [TRAY, BOX, PLATE])
    return RecommendationRequest(**data)


# --- Codes ---------------------------------------------------------------------------


def test_codes_are_normalized():
    candidate = Candidate(artwork_id=1, colors=[" Rojo "], shape="Bandeja", motifs=["Colibrí"])

    assert candidate.colors == ["rojo"]
    assert candidate.shape == "bandeja"
    assert candidate.motifs == ["colibri"]


# --- FeatureVectorizer ---------------------------------------------------------------


def test_identical_items_have_similarity_one():
    candidate = Candidate(**TRAY)
    vectorizer = FeatureVectorizer([candidate])
    vector = vectorizer.candidate_vector(candidate)

    assert vectorizer.similarity(vector, vector) == pytest.approx(1.0)


def test_disjoint_items_have_similarity_zero():
    tray, box = Candidate(**TRAY), Candidate(**BOX)
    vectorizer = FeatureVectorizer([tray, box])

    similarity = vectorizer.similarity(
        vectorizer.candidate_vector(tray), vectorizer.candidate_vector(box)
    )

    assert similarity == 0.0


def test_empty_vector_has_similarity_zero():
    candidate = Candidate(**TRAY)
    vectorizer = FeatureVectorizer([candidate])
    empty = vectorizer.profile_vector(None)

    assert vectorizer.similarity(empty, vectorizer.candidate_vector(candidate)) == 0.0


def test_shape_weighs_more_than_a_color():
    item = Candidate(artwork_id=1, colors=["rojo"], shape="bandeja")
    vectorizer = FeatureVectorizer([item])
    item_vector = vectorizer.candidate_vector(item)

    by_shape = vectorizer.similarity(
        vectorizer.profile_vector(TasteProfile(shapes=["bandeja"])), item_vector
    )
    by_color = vectorizer.similarity(
        vectorizer.profile_vector(TasteProfile(colors=["rojo"])), item_vector
    )

    assert by_shape > by_color


# --- Budget --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("price", "expected"),
    [(80, 1.0), (120, 1.0), (20, 1.0), (150, 0.5), (180, 0.0), (15, 0.5)],
)
def test_budget_fit_inside_and_outside(price, expected):
    budget = Budget(min=20, max=120, currency="USD")
    candidate = Candidate(artwork_id=1, price=price, currency="USD")

    assert budget_fit(budget, candidate) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("budget", "price", "currency"),
    [
        (None, 80, "USD"),
        (Budget(min=20, max=120, currency="USD"), 80, "COP"),
        (Budget(min=20, max=120, currency="USD"), None, "USD"),
        (Budget(currency="USD"), 80, "USD"),
    ],
)
def test_budget_fit_is_unknown_when_not_comparable(budget, price, currency):
    candidate = Candidate(artwork_id=1, price=price, currency=currency)

    assert budget_fit(budget, candidate) is None


def test_budget_min_greater_than_max_is_invalid():
    with pytest.raises(ValueError):
        Budget(min=100, max=10, currency="USD")


# --- Strategies ----------------------------------------------------------------------


def test_content_strategy_ranks_by_tastes_and_explains():
    items = ContentBasedStrategy(NO_DIVERSITY).rank(make_request(profile=PROFILE))

    assert [item.artwork_id for item in items] == [5, 7, 6]
    best = items[0]
    assert best.score > 0.8
    assert best.reasons.colors == ["rojo"]
    assert best.reasons.shape is True
    assert best.reasons.style is True
    assert best.reasons.motifs == ["colibri"]
    assert best.reasons.budget is True
    assert items[-1].reasons.budget is False


def test_content_strategy_is_deterministic():
    request = make_request(profile=PROFILE)

    assert ContentBasedStrategy().rank(request) == ContentBasedStrategy().rank(request)


def test_ties_are_broken_by_popularity_then_id():
    twins = [
        {**TRAY, "artwork_id": 9, "popularity": 1},
        {**TRAY, "artwork_id": 8, "popularity": 1},
        {**TRAY, "artwork_id": 10, "popularity": 5},
    ]
    items = ContentBasedStrategy().rank(make_request(profile=PROFILE, candidates=twins))

    assert [item.artwork_id for item in items] == [10, 8, 9]


def test_view_weight_grows_with_duration():
    short = interaction_weight(Interaction(artwork_id=1, action="VIEW", duration_seconds=5))
    long = interaction_weight(Interaction(artwork_id=1, action="VIEW", duration_seconds=600))
    purchase = interaction_weight(Interaction(artwork_id=1, action="PURCHASE"))

    assert short < long
    assert long == pytest.approx(1.0)
    assert purchase > long


def test_hybrid_strategy_learns_from_interactions():
    request = make_request(interactions=[{"artwork_id": 6, "action": "FAVORITE"}])

    items = HybridStrategy().rank(request)

    assert items[0].artwork_id == 6
    assert items[1].artwork_id == 7  # shares the blue colour and style with the favourite
    assert items[1].reasons.colors == ["azul"]


def test_hybrid_strategy_blends_profile_and_interactions():
    only_profile = ContentBasedStrategy().rank(make_request(profile=PROFILE))
    blended = HybridStrategy().rank(
        make_request(profile=PROFILE, interactions=[{"artwork_id": 7, "action": "PURCHASE"}])
    )

    before = {item.artwork_id: item.score for item in only_profile}
    after = {item.artwork_id: item.score for item in blended}
    assert after[7] > before[7]
    assert blended[0].artwork_id == 5


def test_popularity_strategy_orders_by_popularity():
    items = PopularityStrategy().rank(make_request())

    assert [item.artwork_id for item in items] == [6, 5, 7]
    assert items[0].score == 1.0


# --- Service -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"profile": PROFILE}, "content"),
        ({"profile": PROFILE, "interactions": [{"artwork_id": 5, "action": "VIEW"}]}, "hybrid"),
        ({"interactions": [{"artwork_id": 5, "action": "CART"}]}, "hybrid"),
        ({"interactions": [{"artwork_id": 999, "action": "CART"}]}, "popular"),
        ({}, "popular"),
        ({"profile": {"budget": {"max": 100, "currency": "USD"}}}, "popular"),
    ],
)
def test_service_chooses_strategy(data, expected):
    response = RecommendationService().recommend(make_request(**data))

    assert response.strategy == expected


def test_service_respects_limit():
    response = RecommendationService().recommend(make_request(profile=PROFILE, limit=2))

    assert len(response.items) == 2


# --- Endpoint ------------------------------------------------------------------------


def test_endpoint_returns_contract(client, auth_headers):
    body = {
        "profile": PROFILE,
        "interactions": [{"artwork_id": 5, "action": "VIEW", "duration_seconds": 40}],
        "candidates": [TRAY, BOX],
        "limit": 10,
    }

    response = client.post("/v1/recommendations", json=body, headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["strategy"] == "hybrid"
    assert data["items"][0]["artwork_id"] == 5
    assert data["items"][0]["store_id"] == 2
    assert set(data["items"][0]["reasons"]) == {"colors", "shape", "style", "motifs", "budget"}


def test_endpoint_with_no_candidates_returns_empty_list(client, auth_headers):
    response = client.post("/v1/recommendations", json={}, headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"strategy": "popular", "items": []}


def test_endpoint_requires_api_key(client):
    assert client.post("/v1/recommendations", json={}).status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {"limit": 0},
        {"interactions": [{"artwork_id": 1, "action": "LIKE"}]},
        {"profile": {"budget": {"max": 10, "currency": "dollars"}}},
    ],
)
def test_endpoint_rejects_invalid_input(client, auth_headers, body):
    response = client.post("/v1/recommendations", json=body, headers=auth_headers)

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_request"


# --- Diversity (MMR) ------------------------------------------------------------------


def test_diversity_moves_another_workshop_up():
    # TRAY and PLATE share workshop 2; BOX is from workshop 3.
    plain = ContentBasedStrategy(NO_DIVERSITY).rank(make_request(profile=PROFILE))
    diverse = ContentBasedStrategy().rank(make_request(profile=PROFILE))

    assert [item.artwork_id for item in plain] == [5, 7, 6]
    assert [item.artwork_id for item in diverse] == [5, 6, 7]


def test_diversity_keeps_relevance_scores():
    plain = {
        i.artwork_id: i.score
        for i in ContentBasedStrategy(NO_DIVERSITY).rank(make_request(profile=PROFILE))
    }
    diverse = {
        i.artwork_id: i.score for i in ContentBasedStrategy().rank(make_request(profile=PROFILE))
    }

    assert plain == diverse


def test_one_workshop_cannot_fill_the_top():
    # Five identical pieces from workshop 9 and an almost identical one (no motif) from
    # workshop 4: MMR brings the other workshop up instead of a third duplicate.
    same_store = [{**TRAY, "artwork_id": 100 + n, "store_id": 9} for n in range(5)]
    other = {**TRAY, "artwork_id": 200, "store_id": 4, "motifs": []}
    request = make_request(profile=PROFILE, candidates=[*same_store, other], limit=3)

    plain = ContentBasedStrategy(NO_DIVERSITY).rank(request)
    diverse = ContentBasedStrategy().rank(request)

    assert {item.store_id for item in plain} == {9}
    assert {item.store_id for item in diverse} == {9, 4}
    assert diverse[1].artwork_id == 200


def test_items_without_store_are_not_penalized():
    no_store = [{**TRAY, "artwork_id": 300 + n, "store_id": None} for n in range(3)]
    other = {**PLATE, "artwork_id": 400, "store_id": 4}
    request = make_request(profile=PROFILE, candidates=[*no_store, other], limit=3)

    items = ContentBasedStrategy().rank(request)

    assert [item.artwork_id for item in items] == [300, 301, 302]


def test_maximum_diversity_shows_one_per_workshop_first():
    weights = RecommendationWeights(diversity=1.0)
    candidates = [
        {**TRAY, "artwork_id": 1, "store_id": 1},
        {**TRAY, "artwork_id": 2, "store_id": 1},
        {**PLATE, "artwork_id": 3, "store_id": 2},
        {**BOX, "artwork_id": 4, "store_id": 3},
    ]

    items = ContentBasedStrategy(weights).rank(make_request(profile=PROFILE, candidates=candidates))

    assert [item.store_id for item in items[:3]] == [1, 2, 3]


def test_diversity_comes_from_settings():
    assert RecommendationWeights.from_settings(build_settings(reco_diversity=0.8)).diversity == 0.8


# --- Optional slug --------------------------------------------------------------------


def test_candidate_slug_is_optional():
    assert Candidate(artwork_id=1).slug is None
    assert Candidate(artwork_id=1, slug="bargueno-colonial").slug == "bargueno-colonial"


@pytest.mark.parametrize(
    "bad",
    [
        "Bargueno-Colonial",
        " bargueno",
        "con espacio",
        "tilde-ñ",
        "-inicio",
        "doble--guion",
        "x" * 121,
    ],
)
def test_invalid_slug_is_rejected(bad):
    with pytest.raises(ValueError):
        Candidate(artwork_id=1, slug=bad)


def test_requests_without_slug_work_as_before(client, auth_headers):
    body = {"profile": {"colors": ["rojo"]}, "candidates": [{"artwork_id": 1, "colors": ["rojo"]}]}

    response = client.post("/v1/recommendations", json=body, headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["items"][0]["artwork_id"] == 1
