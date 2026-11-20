"""Input and output models for ``POST /v1/similar`` ("Obras parecidas")."""

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.codes import Slug


class ArtworkRef(BaseModel):
    artwork_id: int
    slug: Slug
    store_id: int | None = None


class SimilarRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "artwork": {"artwork_id": 12, "slug": "jarron-flora-azul"},
                    "candidates": [
                        {"artwork_id": 11, "slug": "bargueno-colonial", "store_id": 1},
                        {
                            "artwork_id": 13,
                            "slug": "jarron-flora-dorada-fondo-negro",
                            "store_id": 1,
                        },
                        {"artwork_id": 31, "slug": "mensajero-ancestral", "store_id": 5},
                    ],
                    "limit": 6,
                }
            ]
        }
    )

    artwork: ArtworkRef = Field(description="La obra de la ficha.")
    candidates: list[ArtworkRef] = Field(
        default_factory=list,
        max_length=500,
        description="Obras que se pueden mostrar (solo las disponibles), con su slug.",
    )
    limit: int = Field(default=6, ge=1, le=50)


class SimilarItem(BaseModel):
    artwork_id: int
    slug: str
    store_id: int | None
    #: Similarity from 0 to 1 (visual and semantic, learned from the photos).
    score: float
    #: Traits both pieces share, in Spanish ("flora densa", "grecas").
    shared_traits: list[str]
    same_master: bool
    explanation: str


class SimilarResponse(BaseModel):
    artwork_id: int
    slug: str
    items: list[SimilarItem]
