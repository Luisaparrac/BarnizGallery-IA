"""Trains the suspicious bid detector (Isolation Forest) on the SYNTHETIC auctions.

Usage::

    python scripts/train_bid_model.py        # data/auctions_synthetic.csv -> models/

1. Rebuilds every bid's context from the CSV (the bidder's earlier bids, the auction state)
   and turns it into features with ``app.auctions.bid_features`` -- exactly what the service
   does in production.
2. Splits by **auction** (70 % train / 30 % test) so bids of one auction never land on both
   sides.
3. Trains an Isolation Forest *without labels*: it learns what usual bids look like and
   scores how unusual a new one is. The labels are only used to evaluate.
4. Evaluates on the test auctions: the model alone, and "model OR strong rule" (what
   ``POST /v1/bids/assess`` does), with precision, recall, F1, confusion matrix and recall
   per kind of manipulation.
5. Saves ``models/bid_anomaly.joblib`` (model + calibration) and
   ``models/bid_anomaly_metrics.json``.

The 0..1 score is a logistic curve centred on the model's own decision threshold: 0.5 is the
boundary between "usual" and "unusual".
"""

import argparse
import csv
import hashlib
import json
import math
import random
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.auctions.bid_features import FEATURE_NAMES, extract_features  # noqa: E402
from app.auctions.bid_rules import BidRules  # noqa: E402
from app.schemas.bids import BidAssessRequest  # noqa: E402

TEST_SHARE = 0.3
N_ESTIMATORS = 200
MODEL_VERSION = 1


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if not rows:
        raise SystemExit(f"{path} está vacío")
    return rows


def build_requests(rows: list[dict[str, Any]]) -> list[tuple[BidAssessRequest, dict[str, Any]]]:
    """One assessment request per bid, with only what was known when it was placed."""
    history: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    ordered = sorted(
        rows, key=lambda row: (int(row["auction_id"]), row["placed_at"], int(row["bid_id"]))
    )
    built = []
    for row in ordered:
        key = (row["auction_id"], row["bidder_id"])
        request = BidAssessRequest(
            auction={
                "auction_id": int(row["auction_id"]),
                "base_price": float(row["base_price"]),
                "current_bid": float(row["current_bid_before"])
                if row["current_bid_before"]
                else None,
                "leader_bidder_id": int(row["leader_before"]) if row["leader_before"] else None,
                "min_increment": float(row["min_increment"]),
                "currency": row["currency"],
                "ends_at": row["ends_at"],
                "last_bid_at": row["last_bid_at_before"] or None,
            },
            bid={
                "bidder_id": int(row["bidder_id"]),
                "amount": float(row["amount"]),
                "placed_at": row["placed_at"],
            },
            bidder={
                "account_created_at": row["account_created_at"],
                "bids": [
                    {
                        "amount": float(p["amount"]),
                        "placed_at": p["placed_at"],
                        "raised_own": p["raised_own"] == "1",
                    }
                    for p in history[key]
                ],
            },
        )
        built.append((request, row))
        history[key].append(row)
    return built


def split_by_auction(items: list, seed: int) -> tuple[list, list]:
    auctions = sorted({int(row["auction_id"]) for _, row in items})
    random.Random(seed).shuffle(auctions)
    test_ids = set(auctions[: round(len(auctions) * TEST_SHARE)])
    train = [item for item in items if int(item[1]["auction_id"]) not in test_ids]
    test = [item for item in items if int(item[1]["auction_id"]) in test_ids]
    return train, test


def matrix(items: list) -> np.ndarray:
    return np.array([extract_features(request).vector() for request, _ in items])


def labels(items: list) -> np.ndarray:
    return np.array([int(row["is_suspicious"]) for _, row in items])


def to_score(raw: np.ndarray, threshold: float, scale: float) -> np.ndarray:
    """Logistic 0..1 score; ``raw == threshold`` gives 0.5."""
    return 1 / (1 + np.exp(-(raw - threshold) / scale))


def summarize(truth: np.ndarray, predicted: np.ndarray, kinds: list[str]) -> dict[str, Any]:
    precision, recall, f1, _ = precision_recall_fscore_support(
        truth, predicted, average="binary", zero_division=0
    )
    tn, fp, fn, tp = confusion_matrix(truth, predicted, labels=[0, 1]).ravel()
    per_kind = {}
    for kind in sorted(set(kinds) - {"normal"}):
        mask = np.array([k == kind for k in kinds])
        per_kind[kind] = round(float(predicted[mask].mean()), 3) if mask.any() else None
    normal = np.array([k == "normal" for k in kinds])
    return {
        "precision": round(float(precision), 3),
        "recall": round(float(recall), 3),
        "f1": round(float(f1), 3),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "recall_by_kind": per_kind,
        "false_positive_rate": round(float(predicted[normal].mean()), 3) if normal.any() else None,
    }


def train(data: Path, models_dir: Path, seed: int) -> dict[str, Any]:
    items = build_requests(load_rows(data))
    train_items, test_items = split_by_auction(items, seed)
    x_train, x_test = matrix(train_items), matrix(test_items)
    y_train, y_test = labels(train_items), labels(test_items)

    contamination = float(np.clip(y_train.mean(), 0.01, 0.4))
    model = IsolationForest(
        n_estimators=N_ESTIMATORS, contamination=contamination, random_state=seed
    ).fit(x_train)

    raw_train = -model.score_samples(x_train)
    threshold = float(-model.offset_)
    scale = float(np.std(raw_train)) or 1.0

    model_pred = (to_score(-model.score_samples(x_test), threshold, scale) >= 0.5).astype(int)
    rule_strong = np.array(
        [int(any(hit.strong for hit in BidRules.evaluate(request))) for request, _ in test_items]
    )
    combined = np.maximum(model_pred, rule_strong)
    kinds = [row["label"] for _, row in test_items]

    data_hash = hashlib.sha256(data.read_bytes()).hexdigest()
    metrics = {
        "model": "IsolationForest",
        "version": MODEL_VERSION,
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "data": {
            "file": data.name,
            "synthetic": True,
            "sha256": data_hash,
            "bids": len(items),
            "auctions": len({row["auction_id"] for _, row in items}),
            "suspicious_share": round(float(labels(items).mean()), 3),
        },
        "split": {
            "by": "auction",
            "seed": seed,
            "train_bids": len(train_items),
            "test_bids": len(test_items),
            "test_suspicious": int(y_test.sum()),
        },
        "params": {"n_estimators": N_ESTIMATORS, "contamination": round(contamination, 3)},
        "features": list(FEATURE_NAMES),
        "test": {
            "model_only": summarize(y_test, model_pred, kinds),
            "model_or_strong_rule": summarize(y_test, combined, kinds),
        },
    }

    models_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "feature_names": list(FEATURE_NAMES),
            "threshold": threshold,
            "scale": scale,
            "version": MODEL_VERSION,
            "sklearn_version": sklearn.__version__,
            "trained_at": metrics["trained_at"],
            "data_sha256": data_hash,
        },
        models_dir / "bid_anomaly.joblib",
        compress=3,
    )
    (models_dir / "bid_anomaly_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return metrics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Entrena el detector de pujas sospechosas.")
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "auctions_synthetic.csv")
    parser.add_argument("--models", type=Path, default=ROOT / "models")
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args(argv)

    metrics = train(args.data, args.models, args.seed)
    size_kb = (args.models / "bid_anomaly.joblib").stat().st_size / 1024
    print(f"Modelo: {args.models / 'bid_anomaly.joblib'} ({size_kb:.0f} KB) — datos SINTÉTICOS")
    for name, result in metrics["test"].items():
        cm = result["confusion_matrix"]
        print(
            f"  {name}: precisión {result['precision']}, recall {result['recall']}, "
            f"F1 {result['f1']} | VP {cm['tp']} FP {cm['fp']} FN {cm['fn']} VN {cm['tn']}"
        )
        print(f"    recall por tipo: {result['recall_by_kind']}")
    if not math.isfinite(metrics["test"]["model_only"]["f1"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
