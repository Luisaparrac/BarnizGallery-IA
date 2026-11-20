"""Common interface for the recommendation algorithms.

Pattern: **Strategy**. ``RecommendationService`` picks one strategy per request and calls
``rank``; it never knows how the score is computed. Concrete strategies only decide how to
build the *user vector* (explicit tastes, interactions, popularity); ``rank`` shares the
scoring, the budget adjustment, the reasons and the diversity-aware ordering (MMR).
The hooks ``prepare`` and ``learned_signal`` let a strategy add what was learned from the
museum's pieces (catalog index); by default they add nothing.
"""

from abc import ABC, abstractmethod
from typing import ClassVar

import numpy as np

from app.recommendations.budget import budget_fit
from app.recommendations.diversity import Ranked, mmr_rerank
from app.recommendations.explanation import explain
from app.recommendations.feature_vectorizer import FeatureVectorizer
from app.recommendations.learned_signals import LearnedSignal
from app.recommendations.recommendation_weights import DEFAULT_WEIGHTS, RecommendationWeights
from app.schemas.recommendations import Candidate, RecommendationItem, RecommendationRequest


class RecommendationStrategy(ABC):
    name: ClassVar[str]

    def __init__(self, weights: RecommendationWeights = DEFAULT_WEIGHTS) -> None:
        self.weights = weights

    def blend(self, relevance: float, fit: float | None) -> float:
        """Mix relevance with the budget fit (when the budget can be compared)."""
        if fit is None:
            return relevance
        share = self.weights.budget_share
        return (1 - share) * relevance + share * fit

    @abstractmethod
    def user_vector(
        self, request: RecommendationRequest, vectorizer: FeatureVectorizer
    ) -> np.ndarray:
        """Vector of what the user likes, in the vectorizer's feature space."""

    def prepare(self, request: RecommendationRequest) -> None:  # noqa: B027 - optional hook
        """Hook: per-request preparation before scoring (nothing by default)."""

    def learned_signal(self, candidate: Candidate) -> LearnedSignal | None:
        """Hook: what the catalog index adds for this candidate (nothing by default)."""
        return None

    def relevance(self, content: float, signal: LearnedSignal | None) -> float:
        if signal is None:
            return content
        semantic, master = self.weights.semantic_weight, self.weights.master_weight
        return (
            (1 - semantic - master) * content + semantic * signal.semantic + master * signal.master
        )

    def rank(self, request: RecommendationRequest) -> list[RecommendationItem]:
        self.prepare(request)
        vectorizer = FeatureVectorizer(request.candidates, request.profile, self.weights.groups)
        user = self.user_vector(request, vectorizer)
        budget = request.profile.budget if request.profile else None

        ranked: list[Ranked] = []
        for candidate in request.candidates:
            similarity = vectorizer.similarity(user, vectorizer.candidate_vector(candidate))
            fit = budget_fit(budget, candidate)
            signal = self.learned_signal(candidate)
            score = self.blend(self.relevance(similarity, signal), fit)
            reasons = vectorizer.matched_reasons(user, candidate)
            reasons.budget = None if fit is None else fit == 1.0
            lead = signal.sentence if signal else None
            if signal is not None and signal.kind == "similar":
                reasons.similar_to = signal.similar_to
            elif signal is not None and signal.kind == "master":
                reasons.master_style = signal.master_slug
            item = RecommendationItem(
                artwork_id=candidate.artwork_id,
                store_id=candidate.store_id,
                score=round(score, 4),
                reasons=reasons,
                explanation=explain(reasons, candidate, lead=lead),
            )
            ranked.append(Ranked(item, candidate.popularity))

        return mmr_rerank(ranked, request.limit, self.weights.diversity)
