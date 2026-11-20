"""Entry point for the suggested price used by the route.

Pattern: **Facade**. The route only calls ``suggest``; the service hides the
``ComparablePriceEstimator``, the optional ``LlmPriceAdvisor`` and the fallback rules:

- At least 3 comparables are always required, with or without a text model
  (else 422 ``not_enough_data``); the text model only adjusts inside their range.
- If the text model fails, the comparables result is returned (``method: "comparables"``)
  instead of an error.

The price is always a suggestion for the artisan, who makes the final decision.
"""

import logging

from app.core.errors import ServiceError
from app.core.request_context import set_field
from app.pricing.auction_pricer import AuctionPricer
from app.pricing.comparable_price_estimator import ComparablePriceEstimator, PriceEstimate
from app.pricing.llm_price_advisor import LlmPriceAdvisor
from app.schemas.pricing import PricingRequest, PricingResponse

logger = logging.getLogger(__name__)

CONFIDENCE_ES = {"low": "baja", "medium": "media", "high": "alta"}


def _money(value: float) -> str:
    return f"{value:,.0f}" if value == int(value) else f"{value:,.2f}"


class PricingService:
    def __init__(self, advisor: LlmPriceAdvisor) -> None:
        self._advisor = advisor

    def suggest(self, request: PricingRequest) -> PricingResponse:
        estimate = ComparablePriceEstimator().estimate(
            request.piece, request.comparables, request.currency
        )
        response = self._suggest_price(request, estimate)
        if request.mode == "auction":
            response.auction = AuctionPricer.suggest(estimate)
        return response

    def _suggest_price(self, request: PricingRequest, estimate: PriceEstimate) -> PricingResponse:
        if self._advisor.enabled:
            try:
                # Only the comparables actually used: never the discarded outliers.
                comparables = list(estimate.comparables)
                advice = self._advisor.advise(request.piece, comparables, estimate)
            except ServiceError as exc:
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
        set_field("pricing_method", method)
        return PricingResponse(
            suggested_price=price,
            min_price=estimate.min_price,
            max_price=estimate.max_price,
            currency=estimate.currency,
            method=method,
            explanation=explanation,
            confidence=estimate.confidence,
        )

    @staticmethod
    def _explain(estimate: PriceEstimate) -> str:
        sold = f", {estimate.sold_count} ya vendidas" if estimate.sold_count else ""
        removed = estimate.outliers_removed
        outliers = ""
        if removed:
            noun = "precio atípico" if removed == 1 else "precios atípicos"
            outliers = f" Se descartaron {removed} {noun}."
        return (
            f"Basado en {estimate.comparables_used} piezas parecidas{sold}, "
            f"con un parecido promedio del {estimate.average_similarity:.0%}.{outliers} "
            f"La mitad de esos precios está entre {_money(estimate.min_price)} y "
            f"{_money(estimate.max_price)} {estimate.currency}. "
            f"Confianza {CONFIDENCE_ES[estimate.confidence]}. "
            "Es una sugerencia: el precio final lo decides tú."
        )
