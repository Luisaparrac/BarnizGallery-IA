"""The trained Isolation Forest, loaded once at startup.

``scripts/train_bid_model.py`` saves ``models/bid_anomaly.joblib``: the model, the feature
names it was trained with and the calibration of the 0..1 score. The file is versioned in
the repo (it is only loaded from there, never from user input). If it is missing, cannot be
read or was trained with other features, the service uses the fixed rules only.
"""

import logging
import math
from pathlib import Path
from typing import Any

from app.auctions.bid_features import FEATURE_NAMES, BidFeatures

logger = logging.getLogger(__name__)


class BidModel:
    def __init__(self, bundle: dict[str, Any]) -> None:
        self._model = bundle["model"]
        self._threshold = float(bundle["threshold"])
        self._scale = float(bundle["scale"]) or 1.0
        self.version = bundle.get("version")
        self.trained_at = bundle.get("trained_at")

    @classmethod
    def from_file(cls, path: Path) -> "BidModel | None":
        if not path.is_file():
            logger.info("Bid model not found; using fixed rules")
            return None
        try:
            import joblib  # imported here: scikit-learn is only loaded when there is a model

            bundle = joblib.load(path)
        except Exception as exc:  # any unreadable or incompatible file: fall back to rules
            logger.warning("Bid model ignored: could not load it (%s)", type(exc).__name__)
            return None
        if not isinstance(bundle, dict) or bundle.get("feature_names") != list(FEATURE_NAMES):
            logger.warning("Bid model ignored: trained with different features")
            return None
        logger.info("Bid model loaded", extra={"version": bundle.get("version")})
        return cls(bundle)

    def score(self, features: BidFeatures) -> float:
        """0..1: 0.5 is the model's own boundary between usual and unusual."""
        raw = -float(self._model.score_samples([features.vector()])[0])
        return 1 / (1 + math.exp(-(raw - self._threshold) / self._scale))
