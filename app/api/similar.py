"""``POST /v1/similar``: works similar to a given one, learned from the museum's pieces."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.openapi_docs import COMMON, error_responses
from app.recommendations.similar_service import SimilarService
from app.schemas.similar import SimilarRequest, SimilarResponse

router = APIRouter(tags=["recommendations"])


def get_similar_service(request: Request) -> SimilarService:
    return SimilarService(request.app.state.catalog_index)


@router.post(
    "/similar",
    response_model=SimilarResponse,
    summary="Obras parecidas a una obra",
    description=(
        'Para la sección "Obras parecidas" de la ficha de una pieza. Compara la obra con '
        "los `candidates` que envía el backend (solo los disponibles, con su `slug`) usando "
        "lo que la IA aprendió de las fotos del museo (índice de obras).\n\n"
        "- `score` va de 0 a 1; `shared_traits` son los rasgos en común, en español.\n"
        "- Los candidatos que no están en el índice se omiten.\n"
        "- Sin índice responde `503 feature_disabled`; si la obra no está en el índice, "
        "`422 not_enough_data`."
    ),
    responses=error_responses(*COMMON, "not_enough_data", "feature_disabled"),
)
def similar(
    request: SimilarRequest,
    service: Annotated[SimilarService, Depends(get_similar_service)],
) -> SimilarResponse:
    return service.similar(request)
