"""``POST /v1/recommendations``: artworks ordered by the customer's tastes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.openapi_docs import COMMON, error_responses
from app.core.config import Settings, get_settings
from app.recommendations.recommendation_service import RecommendationService
from app.recommendations.recommendation_weights import RecommendationWeights
from app.schemas.recommendations import RecommendationRequest, RecommendationResponse

router = APIRouter(tags=["recommendations"])


def get_recommendation_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> RecommendationService:
    return RecommendationService(RecommendationWeights.from_settings(settings))


@router.post(
    "/recommendations",
    response_model=RecommendationResponse,
    summary="Ordena obras según los gustos del cliente",
    description=(
        "Sin entrenamiento: similitud coseno ponderada entre los gustos (códigos de texto) y "
        "las obras, con ajuste por presupuesto y diversidad por taller (MMR).\n\n"
        "- `hybrid`: suma lo que se deduce de las interacciones con obras de `candidates`.\n"
        "- `content`: solo el perfil declarado.\n"
        "- `popular`: sin perfil ni interacciones útiles.\n\n"
        "Cada resultado trae `reasons` y una `explanation` corta en español. `score` es la "
        "relevancia (0 a 1); el orden además aplica diversidad."
    ),
    responses=error_responses(*COMMON),
)
def recommend(
    request: RecommendationRequest,
    service: Annotated[RecommendationService, Depends(get_recommendation_service)],
) -> RecommendationResponse:
    return service.recommend(request)
