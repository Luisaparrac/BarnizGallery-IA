"""``POST /v1/pricing/suggest``: suggested price for an artisan's piece."""

from typing import Annotated

from fastapi import APIRouter, Depends
from openai import OpenAI

from app.api.openapi_docs import COMMON, error_responses
from app.core.config import Settings, get_settings
from app.pricing.llm_price_advisor import LlmPriceAdvisor
from app.pricing.pricing_service import PricingService
from app.pricing.text_models.disabled_text_model import DisabledTextModel
from app.pricing.text_models.openai_text_model import OpenAITextModel
from app.pricing.text_models.text_model import TextModel
from app.schemas.pricing import PricingRequest, PricingResponse

router = APIRouter(tags=["pricing"])

#: The backend waits 10 s for this route, so the text model must answer before that.
TEXT_TIMEOUT_SECONDS = 8.0


def get_text_model(settings: Annotated[Settings, Depends(get_settings)]) -> TextModel:
    if settings.text_provider == "openai":
        client = OpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=min(settings.provider_timeout_seconds, TEXT_TIMEOUT_SECONDS),
            max_retries=0,
        )
        return OpenAITextModel(client, settings.openai_text_model)
    return DisabledTextModel()


def get_pricing_service(
    text_model: Annotated[TextModel, Depends(get_text_model)],
) -> PricingService:
    return PricingService(LlmPriceAdvisor(text_model))


@router.post(
    "/pricing/suggest",
    response_model=PricingResponse,
    summary="Sugiere un precio a partir de piezas comparables",
    description=(
        "Mediana ponderada por parecido (forma, figuras, tamaño) con rango intercuartílico, "
        "después de descartar precios atípicos (IQR). Si hay modelo de texto, ajusta dentro "
        "del rango y redacta la explicación (`comparables+llm`).\n\n"
        "- Exige al menos 3 comparables en la moneda pedida; si no, `422 not_enough_data`. "
        "Nunca inventa un precio.\n"
        "- `confidence` (`low`, `medium`, `high`) depende de cuántos comparables se usaron y "
        "qué tan parecidos son.\n"
        "- Con `mode: \"auction\"` agrega `auction`: precio de salida (percentil 25), reserva "
        "(mediana de los comparables) e incremento mínimo (una décima del rango).
"
        "- Es una sugerencia: el artesano decide."
    ),
    responses=error_responses(*COMMON, "not_enough_data"),
)
def suggest_price(
    request: PricingRequest,
    service: Annotated[PricingService, Depends(get_pricing_service)],
) -> PricingResponse:
    return service.suggest(request)
