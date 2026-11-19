"""Fallback when the customer has no tastes and no usable interactions.

Pattern: **Strategy** (concrete). Orders by ``popularity`` (normalized to ``[0, 1]``),
still applying the budget adjustment if the profile only has a budget.
"""

import numpy as np

from app.recommendations.budget import budget_fit
from app.recommendations.diversity import Ranked, mmr_rerank
from app.recommendations.explanation import explain
from app.recommendations.feature_vectorizer import FeatureVectorizer
from app.recommendations.strategies.recommendation_strategy import RecommendationStrategy
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

        ranked = []
        for candidate in request.candidates:
            popularity = candidate.popularity / top if top > 0 else 0.0
            fit = budget_fit(budget, candidate)
            score = self.blend(popularity, fit)
            reasons = Reasons(budget=None if fit is None else fit == 1.0)
            ranked.append(
                Ranked(
                    RecommendationItem(
                        artwork_id=candidate.artwork_id,
                        store_id=candidate.store_id,
                        score=round(score, 4),
                        reasons=reasons,
                        explanation=explain(reasons, candidate, popular=True),
                    ),
                    candidate.popularity,
                )
            )
        return mmr_rerank(ranked, request.limit, self.weights.diversity)
