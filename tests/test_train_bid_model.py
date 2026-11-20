"""Training script on a small synthetic dataset (fast, no network)."""

import csv
import json
from pathlib import Path

import joblib
import pytest

from app.auctions.bid_features import FEATURE_NAMES
from scripts import generate_auction_data as generator
from scripts import train_bid_model as trainer

ARTWORKS = [
    generator.Artwork("bargueno-colonial", "granja", 900.0),
    generator.Artwork("jarron-colibri", "valderrama", 300.0),
    generator.Artwork("tradicion", "cabrera", 450.0),
]


@pytest.fixture(scope="module")
def dataset(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("data") / "auctions.csv"
    rows = generator.generate(ARTWORKS, auctions_per_work=12, seed=3)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=generator.COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.fixture(scope="module")
def trained(dataset, tmp_path_factory):
    models = tmp_path_factory.mktemp("models")
    return trainer.train(dataset, models, seed=5), models


def test_requests_only_know_the_past(dataset):
    items = trainer.build_requests(trainer.load_rows(dataset))

    for request, row in items:
        assert all(bid.placed_at <= request.bid.placed_at for bid in request.bidder.bids)
        assert str(request.auction.current_bid or "") == str(row["current_bid_before"])


def test_split_keeps_each_auction_on_one_side(dataset):
    items = trainer.build_requests(trainer.load_rows(dataset))

    train, test = trainer.split_by_auction(items, seed=5)

    train_ids = {row["auction_id"] for _, row in train}
    test_ids = {row["auction_id"] for _, row in test}
    assert train_ids and test_ids
    assert not train_ids & test_ids
    assert len(train) + len(test) == len(items)


def test_saves_model_and_metrics(trained):
    metrics, models = trained

    bundle = joblib.load(models / "bid_anomaly.joblib")
    saved = json.loads((models / "bid_anomaly_metrics.json").read_text(encoding="utf-8"))

    assert bundle["feature_names"] == list(FEATURE_NAMES)
    assert {"model", "threshold", "scale", "sklearn_version", "data_sha256"} <= set(bundle)
    assert saved == metrics
    assert saved["data"]["synthetic"] is True
    assert (models / "bid_anomaly.joblib").stat().st_size < 2_000_000


def test_metrics_are_complete_and_sane(trained):
    metrics, _ = trained

    for result in metrics["test"].values():
        assert 0 <= result["precision"] <= 1
        assert 0 <= result["recall"] <= 1
        cm = result["confusion_matrix"]
        assert sum(cm.values()) == metrics["split"]["test_bids"]
    huge_jump = metrics["test"]["model_only"]["recall_by_kind"].get("huge_jump")
    assert huge_jump is None or huge_jump > 0.5  # huge jumps are the easiest to catch


def test_model_separates_obvious_cases(trained):
    _, models = trained
    bundle = joblib.load(models / "bid_anomaly.joblib")
    usual = [[1.05, 1.1, 8.0, 1, 5.5, 0, 2, 9.0, 1.2, 7.0]]
    weird = [[15.0, 18.0, 1.0, 7, 0.1, 4, 9, 3.0, 50.0, 1.0]]

    raw = -bundle["model"].score_samples(usual + weird)
    scores = trainer.to_score(raw, bundle["threshold"], bundle["scale"])

    assert scores[1] > 0.5 > scores[0]


def test_training_is_reproducible(dataset, tmp_path):
    first = trainer.train(dataset, tmp_path / "a", seed=5)
    second = trainer.train(dataset, tmp_path / "b", seed=5)

    assert first["test"] == second["test"]


def test_cli(dataset, tmp_path, capsys):
    assert (
        trainer.main(["--data", str(dataset), "--models", str(tmp_path / "m"), "--seed", "5"]) == 0
    )

    out = capsys.readouterr().out
    assert "SINTÉTICOS" in out
    assert "precisión" in out
