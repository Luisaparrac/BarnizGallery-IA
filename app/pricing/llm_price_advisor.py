"""Optional advisor that refines the comparables estimate with a text model.

It sends the piece, the comparables range and the most similar comparables to a
``TextModel`` and asks for a price *inside* that range plus a short explanation in
Spanish for the artisan. Whatever the model answers, the price is clamped to the range:
the advisor can only move the suggestion, never invent a price without a base.
"""

import json
from dataclasses import dataclass

from app.core.errors import ErrorCode, ServiceError
from app.pricing.comparable_price_estimator import ComparablePriceEstimator, PriceEstimate
from app.pricing.text_models.text_model import TextModel
from app.schemas.pricing import ComparablePiece, PieceDescription

MAX_COMPARABLES_IN_PROMPT = 15
MAX_EXPLANATION_LENGTH = 600

INSTRUCTIONS = (
    "You help artisans of Barniz de Pasto (Mopa-Mopa), a Colombian handicraft of thin "
    "coloured resin sheets applied over carved wood, to price their pieces. You receive the "
    "piece, a price range computed from comparable pieces, and those comparables. Choose a "
    "suggested price that MUST be between min_price and max_price (inclusive), considering "
    "the work hours, technique, size and how similar and sold the comparables are. Write "
    "the explanation in Spanish, in at most 3 short sentences, addressed to the artisan, "
    "and remind them it is only a suggestion. Do not mention prices outside the range."
)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "suggested_price": {"type": "number"},
        "explanation": {"type": "string"},
    },
    "required": ["suggested_price", "explanation"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class PriceAdvice:
    suggested_price: float
    explanation: str


class LlmPriceAdvisor:
    def __init__(self, text_model: TextModel) -> None:
        self._text_model = text_model

    @property
    def enabled(self) -> bool:
        return self._text_model.enabled

    def advise(
        self,
        piece: PieceDescription,
        comparables: list[ComparablePiece],
        estimate: PriceEstimate,
    ) -> PriceAdvice:
        answer = self._text_model.generate_json(
            instructions=INSTRUCTIONS,
            prompt=self._build_prompt(piece, comparables, estimate),
            schema_name="price_advice",
            schema=RESPONSE_SCHEMA,
        )
        try:
            price = float(answer["suggested_price"])
            explanation = str(answer["explanation"]).strip()
        except (KeyError, TypeError, ValueError) as exc:
            raise ServiceError(
                ErrorCode.PROVIDER_ERROR, "El modelo de texto devolvió una respuesta inválida."
            ) from exc
        if not explanation:
            raise ServiceError(
                ErrorCode.PROVIDER_ERROR, "El modelo de texto no devolvió una explicación."
            )

        clamped = min(max(price, estimate.min_price), estimate.max_price)
        return PriceAdvice(
            suggested_price=round(clamped, 2),
            explanation=explanation[:MAX_EXPLANATION_LENGTH],
        )

    @staticmethod
    def _build_prompt(
        piece: PieceDescription,
        comparables: list[ComparablePiece],
        estimate: PriceEstimate,
    ) -> str:
        usable = [item for item in comparables if item.currency == estimate.currency]
        most_similar = sorted(
            usable,
            key=lambda item: ComparablePriceEstimator.similarity(piece, item),
            reverse=True,
        )[:MAX_COMPARABLES_IN_PROMPT]
        payload = {
            "piece": piece.model_dump(exclude_none=True),
            "range": {
                "currency": estimate.currency,
                "min_price": estimate.min_price,
                "median_price": estimate.suggested_price,
                "max_price": estimate.max_price,
                "comparables_used": estimate.comparables_used,
                "sold_count": estimate.sold_count,
            },
            "comparables": [
                item.model_dump(exclude_none=True, exclude={"artwork_id", "currency"})
                for item in most_similar
            ],
        }
        return json.dumps(payload, ensure_ascii=False)
