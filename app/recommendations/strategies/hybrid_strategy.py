"""Mixes declared tastes with the taste inferred from interactions.

Pattern: **Strategy** (concrete). Each interaction adds the vector of the artwork it
refers to, multiplied by the weight of its action (``VIEW`` grows with the viewing time).
That *inferred taste* is normalized to ``[0, 1]`` and blended with the profile vector.
Only interactions with artworks present in ``candidates`` can be used, because the
service is stateless and only knows the features of the candidates it receives.
"""

import numpy as np

from app.recommendations.feature_vectorizer import FeatureVectorizer
from app.recommendations.strategies.recommendation_strategy import RecommendationStrategy
from app.schemas.recommendations import Interaction, InteractionAction, RecommendationRequest

ACTION_WEIGHTS: dict[InteractionAction, float] = {
    InteractionAction.ZOOM: 1.5,
    InteractionAction.SHARE: 2.5,
    InteractionAction.FAVORITE: 3.0,
    InteractionAction.CONTACT: 3.5,
    InteractionAction.CART: 4.0,
    InteractionAction.PURCHASE: 5.0,
}
VIEW_MIN_WEIGHT = 0.2
VIEW_MAX_WEIGHT = 1.0
VIEW_FULL_SECONDS = 120


def interaction_weight(interaction: Interaction) -> float:
    if interaction.action is InteractionAction.VIEW:
        seconds = min(interaction.duration_seconds or 0.0, VIEW_FULL_SECONDS)
        return VIEW_MIN_WEIGHT + (VIEW_MAX_WEIGHT - VIEW_MIN_WEIGHT) * seconds / VIEW_FULL_SECONDS
    return ACTION_WEIGHTS[interaction.action]


class HybridStrategy(RecommendationStrategy):
    name = "hybrid"

    def user_vector(
        self, request: RecommendationRequest, vectorizer: FeatureVectorizer
    ) -> np.ndarray:
        profile = vectorizer.profile_vector(request.profile)
        taste = self.inferred_taste(request, vectorizer)
        if not taste.any():
            return profile
        if not profile.any():
            return taste
        share = self.weights.profile_share
        return share * profile + (1 - share) * taste

    @staticmethod
    def inferred_taste(
        request: RecommendationRequest, vectorizer: FeatureVectorizer
    ) -> np.ndarray:
        candidates = {candidate.artwork_id: candidate for candidate in request.candidates}
        taste = np.zeros(vectorizer.size, dtype=float)
        for interaction in request.interactions:
            candidate = candidates.get(interaction.artwork_id)
            if candidate is not None:
                taste += interaction_weight(interaction) * vectorizer.candidate_vector(candidate)
        peak = taste.max(initial=0.0)
        return taste / peak if peak > 0 else taste
