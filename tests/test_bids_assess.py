"""POST /v1/bids/assess with a small trained model and with the rules alone."""

import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path

import joblib
import pytest
from fastapi.testclient import TestClient

from app.auctions.bid_assessor import UNUSUAL_PATTERN, BidAssessor
from app.auctions.bid_model import BidModel
from app.core.config import get_settings
from app.main import create_app, load_bid_model
from app.schemas.bids import BidAssessRequest
from scripts import generate_auction_data as generator
from scripts import train_bid_model as trainer
from tests.conftest import TEST_API_KEY, build_settings

NOW = datetime(2026, 11, 20, 19, 0, tzinfo=UTC)
HEADERS = {"X-API-Key": TEST_API_KEY}


@pytest.fixture(scope="module")
def model(tmp_path_factory) -> BidModel:
    folder = tmp_path_factory.mktemp("bids")
    data = folder / "auctions.csv"
    rows = generator.generate(
        [generator.Artwork("a", "m", 900.0), generator.Artwork("b", "n", 300.0)], 15, seed=3
    )
    with data.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=generator.COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    trainer.train(data, folder, seed=5)
    return BidModel.from_file(folder / "bid_anomaly.joblib")


def body(amount=130.0, past=(), created=timedelta(days=300), last_bid_seconds=900, **auction):
    return {
        "auction": {
            "auction_id": 7,
            "base_price": 100,
            "current_bid": 120,
            "leader_bidder_id": 55,
            "min_increment": 5,
            "currency": "USD",
            "ends_at": (NOW + timedelta(hours=20)).isoformat(),
            "last_bid_at": (NOW - timedelta(seconds=last_bid_seconds)).isoformat(),
            **auction,
        },
        "bid": {"bidder_id": 81, "amount": amount, "placed_at": NOW.isoformat()},
        "bidder": {"account_created_at": (NOW - created).isoformat(), "bids": list(past)},
    }


def client_with(bid_model) -> TestClient:
    app = create_app(bid_model=bid_model, catalog_index=None)
    settings = build_settings()
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def assess(model, data):
    return BidAssessor(model).assess(BidAssessRequest(**data))


# --- With the trained model -------------------------------------------------------------


def test_usual_bid_is_ok(model):
    result = assess(model, body())

    assert result.status == "OK"
    assert result.method == "model"
    assert result.score < 0.5
    assert result.reasons == []


def test_huge_jump_is_suspicious_with_reason(model):
    result = assess(model, body(amount=1200))

    assert result.status == "SUSPICIOUS"
    assert "Salto de 10 veces la puja actual" in result.reasons
    assert result.score >= 0.9


def test_bot_burst_is_suspicious(model):
    past = [
        {"amount": 100 + i, "placed_at": (NOW - timedelta(seconds=s)).isoformat()}
        for i, s in enumerate((4, 9, 15, 22))
    ]

    result = assess(model, body(amount=125, past=past, last_bid_seconds=4))

    assert result.status == "SUSPICIOUS"
    assert "5 pujas en 22 segundos" in result.reasons


def test_new_account_with_very_high_bid(model):
    result = assess(model, body(amount=600, created=timedelta(hours=3)))

    assert result.status == "SUSPICIOUS"
    assert any(reason.startswith("Cuenta creada hace 3 horas") for reason in result.reasons)


def test_model_alone_gives_a_generic_reason(model, monkeypatch):
    monkeypatch.setattr(model, "score", lambda features: 0.8)

    result = assess(model, body())

    assert result.status == "SUSPICIOUS"
    assert result.reasons == [UNUSUAL_PATTERN]
    assert result.score == 0.8


# --- Rules only ---------------------------------------------------------------------------


def test_without_model_the_rules_decide():
    usual = assess(None, body())
    jump = assess(None, body(amount=1200))
    weak = assess(None, body(amount=400))

    assert (usual.status, usual.method, usual.score) == ("OK", "rules", 0.0)
    assert (jump.status, jump.score) == ("SUSPICIOUS", 0.9)
    assert weak.status == "OK"  # a weak reason alone does not flag the bid
    assert weak.reasons == ["Salto de 3,3 veces la puja actual"]


# --- Endpoint -------------------------------------------------------------------------


def test_endpoint_with_model(model):
    response = client_with(model).post("/v1/bids/assess", json=body(amount=1200), headers=HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUSPICIOUS"
    assert data["method"] == "model"
    assert 0 <= data["score"] <= 1


def test_endpoint_without_model_uses_rules():
    response = client_with(None).post("/v1/bids/assess", json=body(), headers=HEADERS)

    assert response.json() == {"status": "OK", "score": 0.0, "reasons": [], "method": "rules"}


def test_endpoint_requires_api_key():
    assert client_with(None).post("/v1/bids/assess", json=body()).status_code == 401


def test_endpoint_rejects_invalid_input():
    bad = body()
    bad["bid"]["amount"] = -5

    response = client_with(None).post("/v1/bids/assess", json=bad, headers=HEADERS)

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_request"


# --- Loading ----------------------------------------------------------------------------


def test_missing_or_broken_model_falls_back_to_rules(tmp_path):
    broken = tmp_path / "broken.joblib"
    broken.write_bytes(b"not a model")

    assert BidModel.from_file(tmp_path / "missing.joblib") is None
    assert BidModel.from_file(broken) is None


def test_model_with_other_features_is_ignored(tmp_path):
    path = tmp_path / "old.joblib"
    joblib.dump({"model": None, "feature_names": ["jump_ratio"], "threshold": 0, "scale": 1}, path)

    assert BidModel.from_file(path) is None


def test_versioned_model_is_valid_and_loads_from_the_environment(monkeypatch):
    versioned = Path(__file__).resolve().parent.parent / "models" / "bid_anomaly.joblib"
    monkeypatch.setenv("BID_MODEL_PATH", str(versioned))

    assert load_bid_model() is not None
