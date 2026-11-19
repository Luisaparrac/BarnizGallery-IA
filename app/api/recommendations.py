"""``POST /v1/recommendations``: artworks ordered by the customer's tastes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.recommendations.recommendation_service import RecommendationService
from app.recommendations.recommendation_weights import RecommendationWeights
from app.schemas.recommendations import RecommendationRequest, RecommendationResponse

router = APIRouter(tags=["recommendations"])


def get_recommendation_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> RecommendationService:
    return RecommendationService(RecommendationWeights.from_settings(settings))


@router.post("/recommendations", response_model=RecommendationResponse)
def recommend(
    request: RecommendationRequest,
    service: Annotated[RecommendationService, Depends(get_recommendation_service)],
) -> RecommendationResponse:
    return service.recommend(request)
