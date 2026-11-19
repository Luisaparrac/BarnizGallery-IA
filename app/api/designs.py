"""``POST /v1/designs``: design proposals for custom orders."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.designs.design_service import DesignService
from app.designs.image_provider_factory import ImageProviderFactory
from app.schemas.designs import DesignRequest, DesignResponse

router = APIRouter(tags=["designs"])


def get_design_service(settings: Annotated[Settings, Depends(get_settings)]) -> DesignService:
    return DesignService(settings, ImageProviderFactory.create(settings))


# Sync route on purpose: providers are blocking, so FastAPI runs it in its thread pool.
@router.post("/designs", response_model=DesignResponse)
def create_designs(
    request: DesignRequest,
    service: Annotated[DesignService, Depends(get_design_service)],
) -> DesignResponse:
    return service.generate(request)
