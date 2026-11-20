"""Synthetic auction generator: reproducible and with the behaviours it promises."""

import csv
import itertools
from collections import defaultdict
from datetime import datetime, timedelta

import pytest

from scripts import generate_auction_data as generator

ARTWORKS = [
    generator.Artwork("bargueno-colonial", "granja", 900.0),
    generator.Artwork("jarron-colibri", "valderrama", 300.0),
    generator.Artwork("tradicion", "cabrera", 450.0),
]


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    return generator.generate(ARTWORKS, auctions_per_work=20, seed=11)


def by_label(rows, label):
    return [row for row in rows if row["label"] == label]


def when(value: str) -> datetime:
    return datetime.fromisoformat(value)


def test_same_seed_same_data_and_other_seed_differs():
    first = generator.generate(ARTWORKS, auctions_per_work=3, seed=5)

    assert first == generator.generate(ARTWORKS, auctions_per_work=3, seed=5)
    assert first != generator.generate(ARTWORKS, auctions_per_work=3, seed=6)


def test_every_kind_of_behaviour_appears(rows):
    labels = {row["label"] for row in rows}

    assert labels == set(generator.LABELS)
    assert 0.05 < sum(row["is_suspicious"] for row in rows) / len(rows) < 0.4


def test_bids_always_go_up_within_an_auction(rows):
    auctions = defaultdict(list)
    for row in rows:
        auctions[row["auction_id"]].append(row)

    for bids in auctions.values():
        amounts = [bid["amount"] for bid in sorted(bids, key=lambda b: when(b["placed_at"]))]
        assert amounts == sorted(amounts)
        assert bids[0]["current_bid_before"] == ""


def test_normal_bids_use_reasonable_increments(rows):
    for row in by_label(rows, "normal"):
        if row["current_bid_before"] == "":
            continue
        step = row["amount"] - row["current_bid_before"]
        assert row["min_increment"] <= step <= 4 * row["min_increment"]


def test_there_is_legitimate_sniping(rows):
    last_minutes = [
        row
        for row in by_label(rows, "normal")
        if when(row["ends_at"]) - when(row["placed_at"]) <= timedelta(minutes=5)
    ]

    assert len(last_minutes) > 0.1 * len(by_label(rows, "normal"))


def test_shill_bidders_push_with_minimum_steps_and_leave_early(rows):
    for row in by_label(rows, "shill"):
        assert row["amount"] == pytest.approx(row["current_bid_before"] + row["min_increment"])
        assert when(row["ends_at"]) - when(row["placed_at"]) > timedelta(hours=1)


def test_bots_bid_seconds_apart(rows):
    bursts = defaultdict(list)
    for row in by_label(rows, "bot_burst"):
        bursts[(row["auction_id"], row["bidder_id"])].append(when(row["placed_at"]))

    for times in bursts.values():
        times.sort()
        assert 5 <= len(times) <= 9
        assert all((b - a).total_seconds() <= 10 for a, b in itertools.pairwise(times))


def test_huge_jumps_and_new_accounts(rows):
    for row in by_label(rows, "huge_jump"):
        reference = row["current_bid_before"] or row["base_price"]
        assert row["amount"] / reference >= 6

    for row in by_label(rows, "new_account_high"):
        age = when(row["placed_at"]) - when(row["account_created_at"])
        # Created at most 30 hours before the auction, which lasts AUCTION_DAYS.
        assert age < timedelta(hours=30, days=generator.AUCTION_DAYS)
        assert row["amount"] >= 3 * row["base_price"]


def test_raised_own_matches_the_leader(rows):
    for row in rows:
        assert row["raised_own"] == int(str(row["leader_before"]) == str(row["bidder_id"]))


def test_cli_writes_a_csv(tmp_path, capsys):
    frontend = tmp_path / "frontend"
    (frontend / "data").mkdir(parents=True)
    (frontend / "data" / "obras.csv").write_text(
        "maestro;obra ES;precio;precio provisional\n"
        "granja;Bargueño Colonial;;900\n"
        "cabrera;Tradición;450;\n"
        "lasso;Sin Precio;;\n",
        encoding="utf-8-sig",
    )
    out = tmp_path / "auctions.csv"

    assert (
        generator.main(["--frontend", str(frontend), "--out", str(out), "--auctions-per-work", "2"])
        == 0
    )

    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert tuple(rows[0]) == generator.COLUMNS
    assert {row["artwork_slug"] for row in rows} == {"bargueno-colonial", "tradicion"}
    assert "SINTÉTICOS" in capsys.readouterr().out
