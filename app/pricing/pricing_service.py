"""Entry point for the suggested price used by the route.

Pattern: **Facade**. The route only calls ``suggest``; the service hides the
``ComparablePriceEstimator``, the optional ``LlmPriceAdvisor`` and the fallback rules:

- Without a text model, at least 3 comparables are required (else 422 ``not_enough_data``).
- With a text model, 1 comparable is enough to give it a base; it adjusts inside the range.
- If the text model fails and there are at least 3 comparables, the comparables result is
  returned (``method: "comparables"``) instead of an error.

The price is always a suggestion for the artisan, who makes the final decision.
"""

import logging

from app.core.errors import ServiceError
from app.pricing.comparable_price_estimator import (
    DEFAULT_MIN_COMPARABLES,
    ComparablePriceEstimator,
    PriceEstimate,
)
from app.pricing.llm_price_advisor import LlmPriceAdvisor
from app.schemas.pricing import PricingRequest, PricingResponse

logger = logging.getLogger(__name__)

MIN_COMPARABLES_WITH_LLM = 1


def _money(value: float) -> str:
    return f"{value:,.0f}" if value == int(value) else f"{value:,.2f}"


class PricingService:
    def __init__(self, advisor: LlmPriceAdvisor) -> None:
        self._advisor = advisor

    def suggest(self, request: PricingRequest) -> PricingResponse:
        minimum = MIN_COMPARABLES_WITH_LLM if self._advisor.enabled else DEFAULT_MIN_COMPARABLES
        estimate = ComparablePriceEstimator(minimum).estimate(
            request.piece, request.comparables, request.currency
        )

        if self._advisor.enabled:
            try:
                advice = self._advisor.advise(request.piece, request.comparables, estimate)
            except ServiceError as exc:
                if estimate.comparables_used < DEFAULT_MIN_COMPARABLES:
                    raise
                logger.warning("Price advisor failed (%s); using comparables only", exc.code)
            else:
                return self._response(
                    estimate, advice.suggested_price, "comparables+llm", advice.explanation
                )

        return self._response(
            estimate, estimate.suggested_price, "comparables", self._explain(estimate)
        )

    @staticmethod
    def _response(
        estimate: PriceEstimate, price: float, method: str, explanation: str
    ) -> PricingResponse:
        return PricingResponse(
            suggested_price=price,
            min_price=estimate.min_price,
            max_price=estimate.max_price,
            currency=estimate.currency,
            method=method,
            explanation=explanation,
        )

    @staticmethod
    def _explain(estimate: PriceEstimate) -> str:
        sold = f", {estimate.sold_count} ya vendidas" if estimate.sold_count else ""
        return (
            f"Basado en {estimate.comparables_used} piezas parecidas{sold}, "
            f"con un parecido promedio del {estimate.average_similarity:.0%}. "
            f"La mitad de esos precios está entre {_money(estimate.min_price)} y "
            f"{_money(estimate.max_price)} {estimate.currency}. "
            "Es una sugerencia: el precio final lo decides tú."
        )
