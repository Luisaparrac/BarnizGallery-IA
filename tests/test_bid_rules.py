from datetime import UTC, datetime, timedelta

import pytest

from app.auctions.bid_rules import BidRules, RuleHit
from app.schemas.bids import BidAssessRequest

NOW = datetime(2026, 11, 20, 19, 0, tzinfo=UTC)


def make_request(amount=130.0, past=(), current=120.0, leader=55, created=timedelta(days=200)):
    return BidAssessRequest(
        auction={
            "auction_id": 1,
            "base_price": 100,
            "current_bid": current,
            "leader_bidder_id": leader,
            "min_increment": 5,
            "currency": "USD",
            "ends_at": NOW + timedelta(hours=1),
        },
        bid={"bidder_id": 81, "amount": amount, "placed_at": NOW},
        bidder={"account_created_at": NOW - created, "bids": list(past)},
    )


def past(seconds_ago, raised_own=False):
    return {
        "amount": 110,
        "placed_at": NOW - timedelta(seconds=seconds_ago),
        "raised_own": raised_own,
    }


def reasons(request) -> list[str]:
    return [hit.reason for hit in BidRules.evaluate(request)]


def test_normal_bid_has_no_reasons():
    assert BidRules.evaluate(make_request()) == []


def test_huge_jump_is_strong():
    [hit] = BidRules.evaluate(make_request(amount=960))

    assert hit == RuleHit("Salto de 8 veces la puja actual", strong=False)
    [strong] = BidRules.evaluate(make_request(amount=1200))
    assert strong == RuleHit("Salto de 10 veces la puja actual", strong=True)


def test_jump_against_base_price_when_nobody_bid():
    assert reasons(make_request(amount=350, current=None, leader=None)) == [
        "Salto de 3,5 veces el precio base"
    ]


def test_burst_of_bids():
    request = make_request(past=[past(5), past(12), past(20), past(30)])

    [hit] = BidRules.evaluate(request)

    assert hit == RuleHit("5 pujas en 30 segundos", strong=True)


def test_small_burst_is_weak():
    [hit] = BidRules.evaluate(make_request(past=[past(10), past(40)]))

    assert hit.strong is False
    assert hit.reason == "3 pujas en 40 segundos"


def test_new_account_with_high_bid():
    request = make_request(amount=360, current=None, leader=None, created=timedelta(hours=5))

    hits = BidRules.evaluate(request)

    assert (
        RuleHit("Cuenta creada hace 5 horas con una puja de 3,6 veces el precio base", strong=True)
        in hits
    )


def test_new_account_minutes():
    request = make_request(amount=160, current=None, leader=None, created=timedelta(minutes=20))

    assert "Cuenta creada hace 20 minutos con una puja de 1,6 veces el precio base" in reasons(
        request
    )


def test_old_account_with_high_bid_is_not_flagged_for_age():
    request = make_request(amount=360, current=None, leader=None)

    assert not any("Cuenta" in reason for reason in reasons(request))


def test_raising_own_bid_and_many_bids():
    history = [past(600 + i * 100, raised_own=i < 2) for i in range(14)]

    hits = BidRules.evaluate(make_request(past=history, leader=81))

    assert RuleHit("Subió su propia puja 3 veces", strong=False) in hits
    assert RuleHit("Hizo 15 pujas en esta subasta", strong=False) in hits


@pytest.mark.parametrize(
    ("hits", "expected"),
    [
        ([], 0.0),
        ([RuleHit("a", True)], 0.9),
        ([RuleHit("a", False)], 0.35),
        ([RuleHit("a", True), RuleHit("b", False)], 1 - 0.1 * 0.65),
    ],
)
def test_score_combines_hits(hits, expected):
    assert BidRules.score(hits) == pytest.approx(expected)
