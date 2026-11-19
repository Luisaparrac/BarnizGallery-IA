"""Entry point for recommendations used by the route.

Pattern: **Facade** (and the *context* of the Strategy pattern). The route only calls
``recommend``; the service chooses the strategy:

- ``hybrid`` when there are interactions with artworks among the candidates,
- ``content`` when there is only a declared taste profile,
- ``popular`` when there is neither.
"""

from app.recommendations.strategies.content_based_strategy import ContentBasedStrategy
from app.recommendations.strategies.hybrid_strategy import HybridStrategy
from app.recommendations.strategies.popularity_strategy import PopularityStrategy
from app.recommendations.strategies.recommendation_strategy import RecommendationStrategy
from app.schemas.recommendations import RecommendationRequest, RecommendationResponse


class RecommendationService:
    def recommend(self, request: RecommendationRequest) -> RecommendationResponse:
        strategy = self.choose_strategy(request)
        return RecommendationResponse(strategy=strategy.name, items=strategy.rank(request))

    @staticmethod
    def choose_strategy(request: RecommendationRequest) -> RecommendationStrategy:
        candidate_ids = {candidate.artwork_id for candidate in request.candidates}
        if any(interaction.artwork_id in candidate_ids for interaction in request.interactions):
            return HybridStrategy()
        if request.profile is not None and request.profile.has_tastes():
            return ContentBasedStrategy()
        return PopularityStrategy()
