from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    image_provider: Literal["fake", "openai"]
    text_provider: Literal["none", "openai"]
