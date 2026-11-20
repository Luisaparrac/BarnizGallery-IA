"""Input and output models for ``POST /v1/bids/assess``."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.schemas.codes import Currency


class AuctionContext(BaseModel):
    auction_id: int
    base_price: float = Field(gt=0, description="Precio base o de salida.")
    current_bid: float | None = Field(
        default=None, gt=0, description="Puja ganadora actual (null si nadie ha pujado)."
    )
    leader_bidder_id: int | None = Field(
        default=None, description="Quién va ganando ahora (null si nadie ha pujado)."
    )
    min_increment: float = Field(default=1, ge=0)
    currency: Currency
    ends_at: AwareDatetime


class NewBid(BaseModel):
    bidder_id: int
    amount: float = Field(gt=0)
    placed_at: AwareDatetime


class PastBid(BaseModel):
    amount: float = Field(gt=0)
    placed_at: AwareDatetime
    #: True if the bidder was already winning when they placed it (raised their own bid).
    raised_own: bool = False


class BidderHistory(BaseModel):
    account_created_at: AwareDatetime
    #: The bidder's previous bids in THIS auction (any order).
    bids: list[PastBid] = Field(default_factory=list, max_length=500)


class BidAssessRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "auction": {
                        "auction_id": 7,
                        "base_price": 100,
                        "current_bid": 120,
                        "leader_bidder_id": 55,
                        "min_increment": 5,
                        "currency": "USD",
                        "ends_at": "2026-11-20T20:00:00Z",
                    },
                    "bid": {
                        "bidder_id": 81,
                        "amount": 960,
                        "placed_at": "2026-11-20T19:20:00Z",
                    },
                    "bidder": {
                        "account_created_at": "2026-11-20T15:00:00Z",
                        "bids": [],
                    },
                }
            ]
        }
    )

    auction: AuctionContext
    bid: NewBid
    bidder: BidderHistory


class BidAssessResponse(BaseModel):
    status: Literal["OK", "SUSPICIOUS"]
    #: 0 = normal, 1 = very unusual.
    score: float
    #: Spanish reasons for the administrator ("Salto de 8 veces la puja actual").
    reasons: list[str]
    #: ``model`` (Isolation Forest + rules) or ``rules`` (fixed rules only).
    method: Literal["model", "rules"]
