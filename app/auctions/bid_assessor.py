"""Decides whether a new bid deserves the administrator's review.

Pattern: **Facade**. The route only calls ``assess``; the service hides the features, the
trained model and the fixed rules:

- ``SUSPICIOUS`` if the model's score is 0.5 or more, **or** a strong rule fires (for
  example a jump of 10 times the current bid).
- The score is the highest of the model's and the rules' scores.
- The reasons always come from the rules (they say why in Spanish); if only the model finds
  the bid odd, the reason says so.
- Without a model it works with the rules alone (``method: "rules"``).

It never rejects a bid: it only marks it for review.
"""

from app.auctions.bid_features import extract_features
from app.auctions.bid_model import BidModel
from app.auctions.bid_rules import BidRules
from app.core.request_context import set_field
from app.schemas.bids import BidAssessRequest, BidAssessResponse

MODEL_THRESHOLD = 0.5
UNUSUAL_PATTERN = "Patrón poco común frente a las pujas habituales"


class BidAssessor:
    def __init__(self, model: BidModel | None) -> None:
        self._model = model

    def assess(self, request: BidAssessRequest) -> BidAssessResponse:
        hits = BidRules.evaluate(request)
        reasons = [hit.reason for hit in hits]
        strong = any(hit.strong for hit in hits)
        score = BidRules.score(hits)
        method = "rules"

        flagged_by_model = False
        if self._model is not None:
            method = "model"
            model_score = self._model.score(extract_features(request))
            score = max(score, model_score)
            flagged_by_model = model_score >= MODEL_THRESHOLD
            if flagged_by_model and not reasons:
                reasons.append(UNUSUAL_PATTERN)

        status = "SUSPICIOUS" if strong or flagged_by_model else "OK"
        set_field("bid_status", status)
        return BidAssessResponse(
            status=status, score=round(score, 4), reasons=reasons, method=method
        )
