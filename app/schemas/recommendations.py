"""Input and output models for ``POST /v1/recommendations`` (with text codes)."""

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.schemas.codes import Code, CodeList, Currency


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
    store_id: int | None = None
    colors: CodeList
    shape: Code | None = None
    style: Code | None = None
    motifs: CodeList
    price: float | None = Field(default=None, ge=0)
    currency: Currency | None = None
    popularity: float = Field(default=0, ge=0)


class RecommendationRequest(BaseModel):
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


class RecommendationResponse(BaseModel):
    strategy: Literal["content", "hybrid", "popular"]
    items: list[RecommendationItem]
