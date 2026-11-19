"""Fallback when the customer has no tastes and no usable interactions.

Pattern: **Strategy** (concrete). Orders by ``popularity`` (normalized to ``[0, 1]``),
still applying the budget adjustment if the profile only has a budget.
"""

import numpy as np

from app.recommendations.budget import budget_fit
from app.recommendations.feature_vectorizer import FeatureVectorizer
from app.recommendations.strategies.recommendation_strategy import (
    BUDGET_SHARE,
    SIMILARITY_SHARE,
    RecommendationStrategy,
)
from app.schemas.recommendations import Reasons, RecommendationItem, RecommendationRequest


class PopularityStrategy(RecommendationStrategy):
    name = "popular"

    def user_vector(
        self, request: RecommendationRequest, vectorizer: FeatureVectorizer
    ) -> np.ndarray:
        return np.zeros(vectorizer.size, dtype=float)

    def rank(self, request: RecommendationRequest) -> list[RecommendationItem]:
        budget = request.profile.budget if request.profile else None
        top = max((candidate.popularity for candidate in request.candidates), default=0.0)

        items = []
        for candidate in request.candidates:
            popularity = candidate.popularity / top if top > 0 else 0.0
            fit = budget_fit(budget, candidate)
            score = popularity
            if fit is not None:
                score = SIMILARITY_SHARE * popularity + BUDGET_SHARE * fit
            reasons = Reasons(budget=None if fit is None else fit == 1.0)
            items.append(
                RecommendationItem(
                    artwork_id=candidate.artwork_id,
                    store_id=candidate.store_id,
                    score=round(score, 4),
                    reasons=reasons,
                )
            )
        popularity_by_id = {c.artwork_id: c.popularity for c in request.candidates}
        items.sort(key=lambda i: (-i.score, -popularity_by_id[i.artwork_id], i.artwork_id))
        return items[: request.limit]
