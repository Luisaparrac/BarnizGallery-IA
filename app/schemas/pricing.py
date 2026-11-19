"""Input and output models for ``POST /v1/pricing/suggest`` (with text codes)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.codes import Code, CodeList, Currency


class PieceDescription(BaseModel):
    shape: Code
    style: Code | None = None
    colors: CodeList
    motifs: CodeList
    width_cm: float | None = Field(default=None, gt=0, le=1000)
    height_cm: float | None = Field(default=None, gt=0, le=1000)
    depth_cm: float | None = Field(default=None, gt=0, le=1000)
    technique: Code | None = None
    work_hours: float | None = Field(default=None, ge=0, le=10_000)


class ComparablePiece(BaseModel):
    artwork_id: int | None = None
    shape: Code
    style: Code | None = None
    colors: CodeList
    motifs: CodeList
    width_cm: float | None = Field(default=None, gt=0, le=1000)
    height_cm: float | None = Field(default=None, gt=0, le=1000)
    depth_cm: float | None = Field(default=None, gt=0, le=1000)
    price: float = Field(gt=0)
    currency: Currency
    sold: bool = False


class PricingRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "piece": {
                        "shape": "bandeja",
                        "style": "tradicional",
                        "colors": ["rojo"],
                        "motifs": ["colibri"],
                        "width_cm": 30,
                        "height_cm": 30,
                        "technique": "barniz",
                        "work_hours": 20,
                    },
                    "comparables": [
                        {
                            "shape": "bandeja",
                            "motifs": ["colibri"],
                            "width_cm": 28,
                            "height_cm": 28,
                            "price": price,
                            "currency": "USD",
                            "sold": sold,
                        }
                        for price, sold in ((80, True), (95, True), (100, False), (115, False))
                    ],
                    "currency": "USD",
                }
            ]
        }
    )

    piece: PieceDescription
    comparables: list[ComparablePiece] = Field(default_factory=list, max_length=500)
    currency: Currency


class PricingResponse(BaseModel):
    suggested_price: float
    min_price: float
    max_price: float
    currency: str
    method: Literal["comparables", "comparables+llm"]
    explanation: str
    #: low / medium / high, from how many comparables were used and how similar they are.
    confidence: Literal["low", "medium", "high"]
