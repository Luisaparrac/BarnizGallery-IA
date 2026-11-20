"""Generates SYNTHETIC auctions to train the suspicious bid detector.

These are NOT real auctions: MUSEO has no auction history yet. The data imitates
reasonable behaviour and labels a few known kinds of manipulation, so a model can be
trained and evaluated. Usage::

    python scripts/generate_auction_data.py                 # data/auctions_synthetic.csv
    python scripts/generate_auction_data.py --seed 7 --auctions-per-work 4

For each artwork of the frontend's ``data/obras.csv`` (price or provisional price) it
simulates several 3-day auctions:

- **normal**: several bidders, increments of 1 to 3 minimum steps, and a share of bids in
  the last minutes (legitimate sniping); rarely, someone raises their own winning bid.
- **shill** (puja inflada): one account bids right after the others, always with the minimum
  step, to push the price up, and stops well before the close.
- **bot_burst**: 5 to 9 bids from the same account a few seconds apart.
- **huge_jump**: a single bid 6 to 20 times the current bid.
- **new_account_high**: an account created hours ago bids 3 to 8 times the base price.

Everything depends on ``--seed``, so the same seed always gives the same file.
"""

import argparse
import csv
import random
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_catalog_index import slugify  # noqa: E402

AUCTION_DAYS = 3
START = datetime(2026, 1, 5, 15, 0, tzinfo=UTC)
LABELS = ("normal", "shill", "bot_burst", "huge_jump", "new_account_high")
COLUMNS = (
    "auction_id",
    "artwork_slug",
    "master",
    "base_price",
    "min_increment",
    "currency",
    "ends_at",
    "bid_id",
    "bidder_id",
    "account_created_at",
    "placed_at",
    "amount",
    "current_bid_before",
    "leader_before",
    "raised_own",
    "label",
    "is_suspicious",
)
# Chance that an auction contains each kind of manipulation.
INJECTION_CHANCE = {"shill": 0.18, "bot_burst": 0.12, "huge_jump": 0.18, "new_account_high": 0.18}


@dataclass
class Artwork:
    slug: str
    master: str
    price: float


@dataclass
class Bidder:
    bidder_id: int
    account_created_at: datetime
    kind: str


@dataclass
class Attempt:
    """A planned bid; its amount is decided when it happens (it depends on the state)."""

    at: datetime
    bidder: Bidder
    kind: str
    factor: float = 1.0


def read_artworks(frontend: Path) -> list[Artwork]:
    rows = csv.DictReader(
        (frontend / "data" / "obras.csv").open(encoding="utf-8-sig"), delimiter=";"
    )
    artworks = []
    for row in rows:
        raw = (row.get("precio") or row.get("precio provisional") or "").strip()
        price = float(raw.replace(",", ".")) if raw else 0.0
        if price > 0:
            artworks.append(Artwork(slugify(row["obra ES"]), row["maestro"].strip(), price))
    if not artworks:
        raise SystemExit("No hay obras con precio en obras.csv")
    return artworks


class AuctionSimulator:
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)
        self._next_bidder = 1000
        self._next_bid = 1

    def bidder(self, kind: str, starts: datetime, max_age_days: float) -> Bidder:
        self._next_bidder += 1
        if kind == "new_account_high":
            age = timedelta(hours=self.rng.uniform(1, 30))
        elif kind == "shill":
            age = timedelta(days=self.rng.uniform(1, 25))
        else:
            age = timedelta(days=self.rng.uniform(20, max_age_days))
        return Bidder(self._next_bidder, starts - age, kind)

    def plan(self, starts: datetime, ends: datetime) -> list[Attempt]:
        rng = self.rng
        duration = (ends - starts).total_seconds()
        people = [self.bidder("normal", starts, 1500) for _ in range(rng.randint(3, 8))]
        attempts = []
        for _ in range(max(4, int(rng.gauss(16, 5)))):
            if rng.random() < 0.25:  # legitimate sniping in the last 5 minutes
                at = ends - timedelta(seconds=rng.uniform(2, 300))
            else:
                at = starts + timedelta(seconds=rng.uniform(0, duration * 0.97))
            attempts.append(Attempt(at, rng.choice(people), "normal"))
        attempts.sort(key=lambda attempt: attempt.at)

        if rng.random() < INJECTION_CHANCE["shill"]:
            shill = self.bidder("shill", starts, 0)
            usable = [a for a in attempts if a.at < ends - timedelta(hours=2)]
            for anchor in rng.sample(usable, k=min(len(usable), rng.randint(6, 12))):
                attempts.append(
                    Attempt(anchor.at + timedelta(seconds=rng.uniform(20, 240)), shill, "shill")
                )
        if rng.random() < INJECTION_CHANCE["bot_burst"]:
            bot = self.bidder("bot_burst", starts, 900)
            at = starts + timedelta(seconds=rng.uniform(0.1, 0.9) * duration)
            for _ in range(rng.randint(5, 9)):
                at += timedelta(seconds=rng.uniform(2, 9))
                attempts.append(Attempt(at, bot, "bot_burst"))
        if rng.random() < INJECTION_CHANCE["huge_jump"]:
            jumper = self.bidder("huge_jump", starts, 1500)
            at = starts + timedelta(seconds=rng.uniform(0.2, 0.95) * duration)
            attempts.append(Attempt(at, jumper, "huge_jump", rng.uniform(6, 20)))
        if rng.random() < INJECTION_CHANCE["new_account_high"]:
            newbie = self.bidder("new_account_high", starts, 0)
            at = starts + timedelta(seconds=rng.uniform(0.1, 0.9) * duration)
            attempts.append(Attempt(at, newbie, "new_account_high", rng.uniform(3, 8)))

        attempts.sort(key=lambda attempt: (attempt.at, attempt.bidder.bidder_id))
        return attempts

    def auction(self, auction_id: int, artwork: Artwork, starts: datetime) -> Iterator[dict]:
        rng = self.rng
        ends = starts + timedelta(days=AUCTION_DAYS)
        base = round(artwork.price * rng.uniform(0.5, 0.8))
        step = max(1, round(base * 0.05))
        current: float | None = None
        leader: int | None = None

        for attempt in self.plan(starts, ends):
            reference = current or base
            raised_own = leader == attempt.bidder.bidder_id
            if attempt.kind == "normal":
                if raised_own and rng.random() > 0.05:
                    continue  # people rarely raise their own winning bid
                amount = reference + step * rng.choice((1, 1, 1, 2, 2, 3)) + rng.uniform(0, step)
                if current is None:
                    amount = base + rng.uniform(0, step)
            elif attempt.kind in ("shill", "bot_burst"):
                amount = reference + step
            elif attempt.kind == "huge_jump":
                amount = reference * attempt.factor
            else:  # new_account_high
                amount = max(base * attempt.factor, reference + step)

            amount = round(amount, 2)
            self._next_bid += 1
            yield {
                "auction_id": auction_id,
                "artwork_slug": artwork.slug,
                "master": artwork.master,
                "base_price": base,
                "min_increment": step,
                "currency": "USD",
                "ends_at": ends.isoformat(),
                "bid_id": self._next_bid,
                "bidder_id": attempt.bidder.bidder_id,
                "account_created_at": attempt.bidder.account_created_at.isoformat(),
                "placed_at": attempt.at.isoformat(),
                "amount": amount,
                "current_bid_before": "" if current is None else current,
                "leader_before": "" if leader is None else leader,
                "raised_own": int(raised_own),
                "label": attempt.kind,
                "is_suspicious": int(attempt.kind != "normal"),
            }
            current, leader = amount, attempt.bidder.bidder_id


def generate(artworks: list[Artwork], auctions_per_work: int, seed: int) -> list[dict]:
    simulator = AuctionSimulator(seed)
    rows, auction_id = [], 0
    for round_ in range(auctions_per_work):
        for artwork in artworks:
            auction_id += 1
            starts = START + timedelta(days=round_ * 4, hours=auction_id % 24)
            rows.extend(simulator.auction(auction_id, artwork, starts))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera subastas SINTÉTICAS etiquetadas.")
    parser.add_argument("--frontend", type=Path, default=ROOT.parent / "BarnizGallery-Frontend")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "auctions_synthetic.csv")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--auctions-per-work", type=int, default=8)
    args = parser.parse_args(argv)

    rows = generate(read_artworks(args.frontend), args.auctions_per_work, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    counts = {label: sum(row["label"] == label for row in rows) for label in LABELS}
    auctions = len({row["auction_id"] for row in rows})
    suspicious = sum(row["is_suspicious"] for row in rows)
    print(f"Datos SINTÉTICOS: {args.out}")
    print(f"{auctions} subastas, {len(rows)} pujas, semilla {args.seed}")
    print(f"Pujas sospechosas: {suspicious} ({suspicious / len(rows):.1%}) {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
