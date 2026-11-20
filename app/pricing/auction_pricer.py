"""Auction settings recommended from the comparables (nothing invented).

Uses the same estimate as the suggested price (comparables in the currency, without
outliers, weighted by similarity):

- **starting price**: the 25th percentile, the lower end of what similar pieces cost, to
  attract bidders without giving the piece away;
- **reserve**: the weighted median of the comparables, the least the piece should sell for;
- **minimum increment**: one tenth of the interquartile range, rounded, and never below 1
  (the platform's minimum step).
"""

from app.pricing.comparable_price_estimator import PriceEstimate
from app.schemas.pricing import AuctionSuggestion

MIN_INCREMENT = 1
INCREMENT_SHARE_OF_RANGE = 0.1


def _money(value: float) -> str:
    return f"{value:,.0f}" if value == int(value) else f"{value:,.2f}"


class AuctionPricer:
    @staticmethod
    def suggest(estimate: PriceEstimate) -> AuctionSuggestion:
        starting = float(int(estimate.min_price))  # round down: a slightly lower start is safer
        reserve = float(round(estimate.suggested_price))
        spread = estimate.max_price - estimate.min_price
        increment = float(max(MIN_INCREMENT, round(spread * INCREMENT_SHARE_OF_RANGE)))
        currency = estimate.currency
        return AuctionSuggestion(
            starting_price=starting,
            reserve_price=max(starting, reserve),
            min_increment=increment,
            currency=currency,
            explanation=(
                f"Salida en {_money(starting)} {currency}: el 25 % más bajo de los precios de "
                f"piezas parecidas. Reserva en {_money(max(starting, reserve))} {currency}: la "
                f"mediana de esos precios. Incrementos de {_money(increment)} {currency}: una "
                "décima parte del rango de precios. Es una sugerencia: el artesano decide."
            ),
        )
