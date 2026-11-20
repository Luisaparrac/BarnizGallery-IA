"""Fixed, explainable rules for suspicious bids.

They give the Spanish reasons shown to the administrator and are the fallback when the
model is not loaded. A **strong** rule alone makes a bid SUSPICIOUS; a weak one only adds a
reason and raises the score. Thresholds follow the platform settings (for example the
``auction.suspicious_multiplier`` of 10).

The rules score combines hits as independent evidence: ``1 - prod(1 - weight)``.
"""

from dataclasses import dataclass

from app.auctions.bid_features import burst_span_seconds, extract_features
from app.schemas.bids import BidAssessRequest

STRONG_WEIGHT = 0.9
WEAK_WEIGHT = 0.35

STRONG_JUMP = 10.0
WEAK_JUMP = 3.0
STRONG_BURST = 5
WEAK_BURST = 3
NEW_ACCOUNT_DAYS = 2.0
STRONG_NEW_ACCOUNT_RATIO = 3.0
WEAK_NEW_ACCOUNT_RATIO = 1.5
WEAK_OWN_RAISES = 3
WEAK_TOTAL_BIDS = 15


@dataclass(frozen=True)
class RuleHit:
    reason: str
    strong: bool

    @property
    def weight(self) -> float:
        return STRONG_WEIGHT if self.strong else WEAK_WEIGHT


def _times(value: float) -> str:
    """``8`` -> "8", ``3.46`` -> "3,5" (Spanish decimal comma)."""
    if value >= 10 or value == int(value):
        return f"{value:.0f}"
    return f"{value:.1f}".replace(".", ",")


def _age(days: float) -> str:
    hours = days * 24
    if hours < 1:
        return f"{max(1, round(hours * 60))} minutos"
    if hours < 48:
        return f"{round(hours)} horas"
    return f"{round(days)} días"


class BidRules:
    @staticmethod
    def evaluate(request: BidAssessRequest) -> list[RuleHit]:
        features = extract_features(request)
        auction, bid = request.auction, request.bid
        hits: list[RuleHit] = []

        target = "la puja actual" if auction.current_bid else "el precio base"
        if features.jump_ratio >= WEAK_JUMP:
            hits.append(
                RuleHit(
                    f"Salto de {_times(features.jump_ratio)} veces {target}",
                    features.jump_ratio >= STRONG_JUMP,
                )
            )

        if features.bids_last_minute >= WEAK_BURST:
            span = max(1, round(burst_span_seconds(request)))
            hits.append(
                RuleHit(
                    f"{features.bids_last_minute} pujas en {span} segundos",
                    features.bids_last_minute >= STRONG_BURST,
                )
            )

        age_days = (bid.placed_at - request.bidder.account_created_at).total_seconds() / 86_400
        if age_days < NEW_ACCOUNT_DAYS and features.base_ratio >= WEAK_NEW_ACCOUNT_RATIO:
            hits.append(
                RuleHit(
                    f"Cuenta creada hace {_age(max(0.0, age_days))} con una puja de "
                    f"{_times(features.base_ratio)} veces el precio base",
                    features.base_ratio >= STRONG_NEW_ACCOUNT_RATIO,
                )
            )

        if features.own_raises >= WEAK_OWN_RAISES:
            hits.append(RuleHit(f"Subió su propia puja {features.own_raises} veces", False))

        if features.total_bids >= WEAK_TOTAL_BIDS:
            hits.append(RuleHit(f"Hizo {features.total_bids} pujas en esta subasta", False))

        return hits

    @staticmethod
    def score(hits: list[RuleHit]) -> float:
        remaining = 1.0
        for hit in hits:
            remaining *= 1 - hit.weight
        return 1 - remaining
