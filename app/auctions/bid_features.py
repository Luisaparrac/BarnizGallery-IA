"""Turns one bid (with its auction and the bidder's history) into numbers.

The same features are used by the synthetic data generator, by the training script and
by the service, so the model always sees the same thing it was trained on.

All features are bounded or log-scaled so a single extreme value does not dominate.
"""

import math
from dataclasses import astuple, dataclass

from app.schemas.bids import BidAssessRequest

#: Window used to count bursts of bids from the same person.
BURST_WINDOW_SECONDS = 60.0
#: Cap for the raise measured in minimum increments.
MAX_INCREMENT_STEPS = 50.0
#: Caps for time-based features.
MAX_GAP_SECONDS = 3600.0
MAX_ACCOUNT_DAYS = 365.0
MAX_SECONDS_TO_CLOSE = 7 * 86_400.0


@dataclass(frozen=True)
class BidFeatures:
    #: New amount / current winning bid (or base price if there is none).
    jump_ratio: float
    #: New amount / base price.
    base_ratio: float
    #: log(1 + seconds since the bidder's previous bid in this auction), capped at 1 hour.
    log_gap_seconds: float
    #: Bidder's bids (including this one) in the last 60 seconds.
    bids_last_minute: int
    #: log(1 + account age in days), capped at a year.
    log_account_days: float
    #: Times the bidder raised their own winning bid (including this one).
    own_raises: int
    #: Bidder's total bids in this auction (including this one).
    total_bids: int
    #: log(1 + seconds left until the auction closes).
    log_seconds_to_close: float
    #: Raise over the current bid measured in minimum increments (capped at 50).
    increment_steps: float
    #: log(1 + seconds since the auction's last bid by anyone), capped at 1 hour.
    log_gap_any_seconds: float

    def vector(self) -> list[float]:
        return [float(value) for value in astuple(self)]


FEATURE_NAMES: tuple[str, ...] = tuple(BidFeatures.__dataclass_fields__)


def extract_features(request: BidAssessRequest) -> BidFeatures:
    auction, bid, bidder = request.auction, request.bid, request.bidder
    reference = auction.current_bid or auction.base_price
    previous = sorted(past.placed_at for past in bidder.bids if past.placed_at <= bid.placed_at)

    gap = MAX_GAP_SECONDS
    if previous:
        gap = min(MAX_GAP_SECONDS, (bid.placed_at - previous[-1]).total_seconds())
    in_window = [
        moment
        for moment in previous
        if (bid.placed_at - moment).total_seconds() <= BURST_WINDOW_SECONDS
    ]
    account_days = (bid.placed_at - bidder.account_created_at).total_seconds() / 86_400
    to_close = (auction.ends_at - bid.placed_at).total_seconds()
    raising_now = auction.leader_bidder_id is not None and auction.leader_bidder_id == bid.bidder_id
    steps = (bid.amount - reference) / auction.min_increment if auction.min_increment > 0 else 0.0
    gap_any = MAX_GAP_SECONDS
    if auction.last_bid_at is not None:
        gap_any = min(MAX_GAP_SECONDS, (bid.placed_at - auction.last_bid_at).total_seconds())

    return BidFeatures(
        jump_ratio=bid.amount / reference,
        base_ratio=bid.amount / auction.base_price,
        log_gap_seconds=math.log1p(max(0.0, gap)),
        bids_last_minute=len(in_window) + 1,
        log_account_days=math.log1p(min(MAX_ACCOUNT_DAYS, max(0.0, account_days))),
        own_raises=sum(past.raised_own for past in bidder.bids) + int(raising_now),
        total_bids=len(bidder.bids) + 1,
        log_seconds_to_close=math.log1p(min(MAX_SECONDS_TO_CLOSE, max(0.0, to_close))),
        increment_steps=min(MAX_INCREMENT_STEPS, max(0.0, steps)),
        log_gap_any_seconds=math.log1p(max(0.0, gap_any)),
    )


def burst_span_seconds(request: BidAssessRequest) -> float:
    """Seconds between the oldest bid of the last-minute burst and the new bid."""
    bid = request.bid
    window = [
        past.placed_at
        for past in request.bidder.bids
        if 0 <= (bid.placed_at - past.placed_at).total_seconds() <= BURST_WINDOW_SECONDS
    ]
    return (bid.placed_at - min(window)).total_seconds() if window else 0.0
