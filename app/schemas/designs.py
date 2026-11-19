"""Input and output models for ``POST /v1/designs``."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


class DesignColor(BaseModel):
    name: ShortText
    hex: Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]


class DesignRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "request_id": 42,
                    "title": "Bandeja para mi abuela",
                    "description": "Bandeja redonda con colibríes y flores",
                    "shape": "Bandeja",
                    "style": "Tradicional",
                    "colors": [{"name": "Rojo", "hex": "#B3261E"}],
                    "motifs": ["Colibrí", "Flores"],
                    "size_notes": "unos 30 cm",
                    "language": "es",
                    "count": 1,
                }
            ]
        }
    )

    request_id: int = Field(ge=1, description="Id del encargo en el backend (solo registro).")
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] = ""
    shape: ShortText
    style: ShortText
    colors: list[DesignColor] = Field(default_factory=list, max_length=8)
    motifs: list[ShortText] = Field(default_factory=list, max_length=10)
    size_notes: Notes | None = None
    language: Literal["es", "en"] = "es"
    count: int = Field(
        default=1, ge=1, description="Imágenes a generar (máximo MAX_IMAGES_PER_REQUEST)."
    )


class GeneratedImage(BaseModel):
    image_base64: str
    mime_type: str = "image/png"
    #: ``top``, ``three_quarter`` or ``detail`` when several images were requested.
    composition: str | None = None
    #: Exact prompt sent for this image.
    prompt: str | None = None


class DesignResponse(BaseModel):
    provider: Literal["fake", "openai"]
    model: str
    prompt: str
    images: list[GeneratedImage]
