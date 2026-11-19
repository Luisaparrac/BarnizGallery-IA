"""Recommends by similarity to the tastes the customer declared.

Pattern: **Strategy** (concrete). The user vector is the binary vector of the profile's
colours, shapes, styles and motifs. No training: only weighted cosine similarity plus
the budget adjustment shared by every strategy.
"""

import numpy as np

from app.recommendations.feature_vectorizer import FeatureVectorizer
from app.recommendations.strategies.recommendation_strategy import RecommendationStrategy
from app.schemas.recommendations import RecommendationRequest


class ContentBasedStrategy(RecommendationStrategy):
    name = "content"

    def user_vector(
        self, request: RecommendationRequest, vectorizer: FeatureVectorizer
    ) -> np.ndarray:
        return vectorizer.profile_vector(request.profile)
