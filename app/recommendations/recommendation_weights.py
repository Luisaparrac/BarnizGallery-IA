"""Tunable weights of the recommender, read from the environment.

Defaults reproduce the original behaviour; ``Settings`` lets them be changed without
touching code (``RECO_WEIGHT_*``, ``RECO_BUDGET_SHARE``, ``RECO_PROFILE_SHARE``).
"""

from dataclasses import dataclass

from app.core.config import Settings


@dataclass(frozen=True)
class RecommendationWeights:
    #: Weight of each feature group in the weighted cosine similarity.
    color: float = 1.0
    shape: float = 1.5
    style: float = 1.2
    motif: float = 1.3
    #: Share of the final score given to the budget fit (the rest is similarity).
    budget_share: float = 0.15
    #: In the hybrid strategy, share of the declared profile vs. inferred taste.
    profile_share: float = 0.6

    @property
    def groups(self) -> dict[str, float]:
        return {"color": self.color, "shape": self.shape, "style": self.style, "motif": self.motif}

    @classmethod
    def from_settings(cls, settings: Settings) -> "RecommendationWeights":
        return cls(
            color=settings.reco_weight_color,
            shape=settings.reco_weight_shape,
            style=settings.reco_weight_style,
            motif=settings.reco_weight_motif,
            budget_share=settings.reco_budget_share,
            profile_share=settings.reco_profile_share,
        )


DEFAULT_WEIGHTS = RecommendationWeights()
