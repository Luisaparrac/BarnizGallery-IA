"""Common error body, documented in OpenAPI for every route."""

from pydantic import BaseModel, ConfigDict, Field


class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"code": "invalid_request", "message": "La solicitud no es válida."}]
        }
    )

    code: str = Field(description="Código estable en inglés para decidir en el backend.")
    message: str = Field(description="Mensaje en español que se puede mostrar a una persona.")
