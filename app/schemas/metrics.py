"""Output model for ``GET /v1/metrics``."""

from pydantic import BaseModel


class RouteMetrics(BaseModel):
    requests: int
    errors: int
    avg_latency_ms: float
    error_codes: dict[str, int]


class EstimatedCost(BaseModel):
    images: float
    text: float
    total: float


class TodayMetrics(BaseModel):
    date: str
    images: dict[str, int]
    text_calls: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: EstimatedCost


class ImageBudgetMetrics(BaseModel):
    daily_image_limit: int
    paid_images_used_today: int
    remaining_today: int


class MetricsResponse(BaseModel):
    since: str
    routes: dict[str, RouteMetrics]
    today: TodayMetrics
    image_budget: ImageBudgetMetrics
