import math
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.auctions.bid_features import FEATURE_NAMES, burst_span_seconds, extract_features
from app.schemas.bids import BidAssessRequest

NOW = datetime(2026, 11, 20, 19, 0, tzinfo=UTC)


def make_request(amount=130.0, past=(), current=120.0, leader=55, created_days=200, **auction):
    return BidAssessRequest(
        auction={
            "auction_id": 1,
            "base_price": 100,
            "current_bid": current,
            "leader_bidder_id": leader,
            "min_increment": 5,
            "currency": "USD",
            "ends_at": NOW + timedelta(hours=1),
            **auction,
        },
        bid={"bidder_id": 81, "amount": amount, "placed_at": NOW},
        bidder={"account_created_at": NOW - timedelta(days=created_days), "bids": list(past)},
    )


def past_bid(seconds_ago, amount=110.0, raised_own=False):
    return {
        "amount": amount,
        "placed_at": NOW - timedelta(seconds=seconds_ago),
        "raised_own": raised_own,
    }


def test_normal_bid_features():
    features = extract_features(make_request())

    assert features.jump_ratio == pytest.approx(130 / 120)
    assert features.base_ratio == pytest.approx(1.3)
    assert features.log_gap_seconds == pytest.approx(math.log1p(3600))
    assert features.bids_last_minute == 1
    assert features.own_raises == 0
    assert features.total_bids == 1
    assert features.log_seconds_to_close == pytest.approx(math.log1p(3600))


def test_first_bid_is_compared_with_the_base_price():
    features = extract_features(make_request(amount=150, current=None, leader=None))

    assert features.jump_ratio == pytest.approx(1.5)


def test_burst_counts_bids_in_the_last_minute():
    request = make_request(
        past=[past_bid(5), past_bid(12), past_bid(25), past_bid(30), past_bid(200)]
    )

    features = extract_features(request)

    assert features.bids_last_minute == 5
    assert features.total_bids == 6
    assert features.log_gap_seconds == pytest.approx(math.log1p(5))
    assert burst_span_seconds(request) == 30


def test_own_raises_include_the_current_one():
    request = make_request(past=[past_bid(400, raised_own=True), past_bid(800)], leader=81)

    assert extract_features(request).own_raises == 2


def test_new_account_and_closing_time():
    request = make_request(created_days=0.1, ends_at=NOW + timedelta(seconds=20))

    features = extract_features(request)

    assert features.log_account_days == pytest.approx(math.log1p(0.1))
    assert features.log_seconds_to_close == pytest.approx(math.log1p(20))


def test_values_are_bounded():
    request = make_request(created_days=5000, ends_at=NOW - timedelta(minutes=5))

    features = extract_features(request)

    assert features.log_account_days == pytest.approx(math.log1p(365))
    assert features.log_seconds_to_close == 0


def test_future_bids_in_history_are_ignored():
    request = make_request(past=[past_bid(-30)])

    assert extract_features(request).bids_last_minute == 1


def test_vector_follows_feature_names():
    features = extract_features(make_request())

    assert len(features.vector()) == len(FEATURE_NAMES) == 10
    assert FEATURE_NAMES[0] == "jump_ratio"


def test_dates_must_have_timezone():
    with pytest.raises(ValidationError):
        BidAssessRequest(
            auction={
                "auction_id": 1,
                "base_price": 1,
                "currency": "USD",
                "ends_at": "2026-11-20T20:00:00",
            },
            bid={"bidder_id": 1, "amount": 2, "placed_at": "2026-11-20T19:00:00Z"},
            bidder={"account_created_at": "2026-01-01T00:00:00Z"},
        )


def test_increment_in_minimum_steps():
    assert extract_features(make_request(amount=125)).increment_steps == pytest.approx(1.0)
    assert extract_features(make_request(amount=6000)).increment_steps == 50.0
    assert extract_features(make_request(amount=110)).increment_steps == 0.0


def test_gap_since_the_auctions_last_bid():
    quick = make_request(last_bid_at=NOW - timedelta(seconds=40))

    assert extract_features(quick).log_gap_any_seconds == pytest.approx(math.log1p(40))
    assert extract_features(make_request()).log_gap_any_seconds == pytest.approx(math.log1p(3600))
