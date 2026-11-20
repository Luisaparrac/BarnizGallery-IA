"""``POST /v1/bids/assess``: marks suspicious bids for the administrator (never rejects)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.openapi_docs import COMMON, error_responses
from app.auctions.bid_assessor import BidAssessor
from app.schemas.bids import BidAssessRequest, BidAssessResponse

router = APIRouter(tags=["auctions"])


def get_bid_assessor(request: Request) -> BidAssessor:
    return BidAssessor(request.app.state.bid_model)


@router.post(
    "/bids/assess",
    response_model=BidAssessResponse,
    summary="Evalúa si una puja es sospechosa",
    description=(
        "El backend la llama **antes de guardar cada puja**. Combina un detector entrenado "
        "(Isolation Forest, con datos sintéticos) con reglas fijas.\n\n"
        "- `SUSPICIOUS` si el detector la ve muy poco común o si hay una señal clara (salto de "
        "10 veces la puja actual, 5 pujas en un minuto, cuenta nueva con un monto muy alto).\n"
        "- `reasons` explica por qué, en español, para el administrador.\n"
        "- **Nunca rechaza:** la puja se guarda igual y, si es `SUSPICIOUS`, queda marcada "
        "para revisión.\n"
        '- Sin modelo responde con las reglas fijas (`method: "rules"`).'
    ),
    responses=error_responses(*COMMON),
)
def assess_bid(
    request: BidAssessRequest,
    assessor: Annotated[BidAssessor, Depends(get_bid_assessor)],
) -> BidAssessResponse:
    return assessor.assess(request)
