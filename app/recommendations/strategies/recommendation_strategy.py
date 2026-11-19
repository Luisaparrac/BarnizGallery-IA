"""Common interface for the recommendation algorithms.

Pattern: **Strategy**. ``RecommendationService`` picks one strategy per request and calls
``rank``; it never knows how the score is computed. Concrete strategies only decide how to
build the *user vector* (explicit tastes, interactions, popularity); ``rank`` shares the
scoring, the budget adjustment, the reasons and the deterministic ordering.
"""

from abc import ABC, abstractmethod
from typing import ClassVar

import numpy as np

from app.recommendations.budget import budget_fit
from app.recommendations.feature_vectorizer import FeatureVectorizer
from app.schemas.recommendations import RecommendationItem, RecommendationRequest

SIMILARITY_SHARE = 0.85
BUDGET_SHARE = 0.15


class RecommendationStrategy(ABC):
    name: ClassVar[str]

    @abstractmethod
    def user_vector(
        self, request: RecommendationRequest, vectorizer: FeatureVectorizer
    ) -> np.ndarray:
        """Vector of what the user likes, in the vectorizer's feature space."""

    def rank(self, request: RecommendationRequest) -> list[RecommendationItem]:
        vectorizer = FeatureVectorizer(request.candidates, request.profile)
        user = self.user_vector(request, vectorizer)
        budget = request.profile.budget if request.profile else None

        scored: list[tuple[float, float, RecommendationItem]] = []
        for candidate in request.candidates:
            similarity = vectorizer.similarity(user, vectorizer.candidate_vector(candidate))
            fit = budget_fit(budget, candidate)
            score = similarity
            if fit is not None:
                score = SIMILARITY_SHARE * similarity + BUDGET_SHARE * fit
            reasons = vectorizer.matched_reasons(user, candidate)
            reasons.budget = None if fit is None else fit == 1.0
            item = RecommendationItem(
                artwork_id=candidate.artwork_id,
                store_id=candidate.store_id,
                score=round(score, 4),
                reasons=reasons,
            )
            scored.append((item.score, candidate.popularity, item))

        # Highest score first; ties by popularity, then by id, so the order is stable.
        scored.sort(key=lambda entry: (-entry[0], -entry[1], entry[2].artwork_id))
        return [item for _, _, item in scored[: request.limit]]
