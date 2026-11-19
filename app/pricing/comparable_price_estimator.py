"""Estimates a price range from similar pieces that already have a price.

The suggested price is the **weighted median** of the comparables' prices and the range
is the weighted **interquartile range** (25th to 75th percentile). Each comparable weighs
more the more it resembles the piece:

- same shape (45 %),
- shared motifs, Jaccard index (25 %),
- similar size, ratio of the areas (30 %),

and sold pieces weigh 25 % more, because their price was accepted by a buyer.

Before weighting, **price outliers are removed** with Tukey's rule: prices outside
``[Q1 - 1.5·IQR, Q3 + 1.5·IQR]`` are discarded (only with 4 or more comparables, and only
if at least the minimum number remains). A typo such as 10000 instead of 100 no longer
drags the suggestion. Only
comparables in the requested currency are used: prices are never converted. With fewer
than ``min_comparables`` usable pieces it raises ``not_enough_data`` instead of
inventing a price.
"""

from dataclasses import dataclass

import numpy as np

from app.core.errors import ErrorCode, ServiceError
from app.schemas.pricing import ComparablePiece, PieceDescription

SHAPE_WEIGHT = 0.45
MOTIF_WEIGHT = 0.25
SIZE_WEIGHT = 0.30
#: Similarity used for a part that cannot be compared (unknown size, no motifs).
NEUTRAL_SIMILARITY = 0.5
#: Every comparable keeps at least this weight, so a single odd piece cannot dominate.
MIN_WEIGHT = 0.1
SOLD_BONUS = 1.25
DEFAULT_MIN_COMPARABLES = 3
#: Tukey's fences: values beyond 1.5 interquartile ranges from the quartiles are outliers.
IQR_FENCE = 1.5
MIN_FOR_OUTLIERS = 4


@dataclass(frozen=True)
class PriceEstimate:
    suggested_price: float
    min_price: float
    max_price: float
    currency: str
    comparables_used: int
    sold_count: int
    average_similarity: float
    outliers_removed: int = 0
    #: The comparables actually used (same currency, without outliers).
    comparables: tuple[ComparablePiece, ...] = ()


def _area(width: float | None, height: float | None) -> float | None:
    return width * height if width and height else None


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, quantile: float) -> float:
    """Smallest value whose cumulative weight reaches ``quantile`` of the total."""
    order = np.argsort(values, kind="stable")
    cumulative = np.cumsum(weights[order]) / weights.sum()
    position = int(np.searchsorted(cumulative, quantile - 1e-9))
    return float(values[order][min(position, len(values) - 1)])


def remove_outliers(
    comparables: list[ComparablePiece], keep_at_least: int
) -> tuple[list[ComparablePiece], int]:
    """Drop prices outside Tukey's fences; return the kept pieces and how many were dropped."""
    if len(comparables) < MIN_FOR_OUTLIERS:
        return comparables, 0
    prices = np.array([item.price for item in comparables], dtype=float)
    q1, q3 = np.percentile(prices, [25, 75])
    spread = q3 - q1
    low, high = q1 - IQR_FENCE * spread, q3 + IQR_FENCE * spread
    kept = [item for item in comparables if low <= item.price <= high]
    if len(kept) < keep_at_least:
        return comparables, 0
    return kept, len(comparables) - len(kept)


class ComparablePriceEstimator:
    def __init__(self, min_comparables: int = DEFAULT_MIN_COMPARABLES) -> None:
        self._min_comparables = min_comparables

    @staticmethod
    def similarity(piece: PieceDescription, comparable: ComparablePiece) -> float:
        """Similarity in ``[0, 1]`` by shape, motifs and size."""
        shape = 1.0 if piece.shape == comparable.shape else 0.0

        motifs_a, motifs_b = set(piece.motifs), set(comparable.motifs)
        if motifs_a or motifs_b:
            motifs = len(motifs_a & motifs_b) / len(motifs_a | motifs_b)
        else:
            motifs = NEUTRAL_SIMILARITY

        area_a = _area(piece.width_cm, piece.height_cm)
        area_b = _area(comparable.width_cm, comparable.height_cm)
        size = NEUTRAL_SIMILARITY
        if area_a and area_b:
            size = min(area_a, area_b) / max(area_a, area_b)

        return SHAPE_WEIGHT * shape + MOTIF_WEIGHT * motifs + SIZE_WEIGHT * size

    def estimate(
        self, piece: PieceDescription, comparables: list[ComparablePiece], currency: str
    ) -> PriceEstimate:
        usable = [comparable for comparable in comparables if comparable.currency == currency]
        if len(usable) < self._min_comparables:
            raise ServiceError(
                ErrorCode.NOT_ENOUGH_DATA,
                f"Se necesitan al menos {self._min_comparables} piezas comparables en {currency} "
                f"para sugerir un precio; llegaron {len(usable)}.",
            )
        usable, removed = remove_outliers(usable, keep_at_least=self._min_comparables)

        similarities = np.array([self.similarity(piece, item) for item in usable])
        weights = MIN_WEIGHT + (1 - MIN_WEIGHT) * similarities
        weights *= np.array([SOLD_BONUS if item.sold else 1.0 for item in usable])
        prices = np.array([item.price for item in usable], dtype=float)

        low = _weighted_quantile(prices, weights, 0.25)
        median = _weighted_quantile(prices, weights, 0.5)
        high = _weighted_quantile(prices, weights, 0.75)

        return PriceEstimate(
            suggested_price=round(median, 2),
            min_price=round(low, 2),
            max_price=round(high, 2),
            currency=currency,
            comparables_used=len(usable),
            sold_count=sum(item.sold for item in usable),
            average_similarity=round(float(similarities.mean()), 2),
            outliers_removed=removed,
            comparables=tuple(usable),
        )
