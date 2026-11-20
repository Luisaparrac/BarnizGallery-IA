"""Input and output models for ``POST /v1/recommendations`` (with text codes)."""

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.codes import Code, CodeList, Currency, Slug


class Budget(BaseModel):
    min: float | None = Field(default=None, ge=0)
    max: float | None = Field(default=None, ge=0)
    currency: Currency

    @model_validator(mode="after")
    def _check_range(self) -> Self:
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("budget.min must be <= budget.max")
        return self


class TasteProfile(BaseModel):
    colors: CodeList
    shapes: CodeList
    styles: CodeList
    motifs: CodeList
    budget: Budget | None = None

    def has_tastes(self) -> bool:
        return bool(self.colors or self.shapes or self.styles or self.motifs)


class InteractionAction(StrEnum):
    VIEW = "VIEW"
    ZOOM = "ZOOM"
    FAVORITE = "FAVORITE"
    CART = "CART"
    PURCHASE = "PURCHASE"
    SHARE = "SHARE"
    CONTACT = "CONTACT"


class Interaction(BaseModel):
    artwork_id: int
    action: InteractionAction
    duration_seconds: float | None = Field(default=None, ge=0)


class Candidate(BaseModel):
    artwork_id: int
    #: Optional slug of the work in the catalog index (``bargueno-colonial``). With it, the
    #: hybrid strategy can also use what the AI learned from the museum's real pieces.
    slug: Slug | None = None
    store_id: int | None = None
    colors: CodeList
    shape: Code | None = None
    style: Code | None = None
    motifs: CodeList
    price: float | None = Field(default=None, ge=0)
    currency: Currency | None = None
    popularity: float = Field(default=0, ge=0)


class RecommendationRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "profile": {
                        "colors": ["rojo", "verde"],
                        "shapes": ["bandeja"],
                        "styles": ["tradicional"],
                        "motifs": ["colibri"],
                        "budget": {"min": 20, "max": 120, "currency": "USD"},
                    },
                    "interactions": [
                        {"artwork_id": 5, "action": "VIEW", "duration_seconds": 40}
                    ],
                    "candidates": [
                        {
                            "artwork_id": 5,
                            "store_id": 2,
                            "colors": ["rojo", "amarillo"],
                            "shape": "bandeja",
                            "style": "tradicional",
                            "motifs": ["colibri"],
                            "price": 80,
                            "currency": "USD",
                            "popularity": 12,
                        }
                    ],
                    "limit": 10,
                }
            ]
        }
    )

    profile: TasteProfile | None = None
    interactions: list[Interaction] = Field(default_factory=list, max_length=1000)
    candidates: list[Candidate] = Field(default_factory=list, max_length=2000)
    limit: int = Field(default=10, ge=1, le=100)


class Reasons(BaseModel):
    colors: list[str] = Field(default_factory=list)
    shape: bool = False
    style: bool = False
    motifs: list[str] = Field(default_factory=list)
    #: ``None`` when there is no budget or the price/currency cannot be compared.
    budget: bool | None = None


class RecommendationItem(BaseModel):
    artwork_id: int
    store_id: int | None
    score: float
    reasons: Reasons
    #: Short Spanish sentence for the customer ("Coincide con lo que te gusta: ...").
    explanation: str = ""


class RecommendationResponse(BaseModel):
    strategy: Literal["content", "hybrid", "popular"]
    items: list[RecommendationItem]
