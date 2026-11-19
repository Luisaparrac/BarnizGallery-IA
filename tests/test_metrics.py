from datetime import UTC, datetime, timedelta

from app.core.metrics import MetricsRegistry
from tests.conftest import TEST_API_KEY

PAYLOAD = {"request_id": 1, "title": "x", "shape": "Bandeja", "style": "Tradicional"}
PRICES = {"image_cost_usd": 0.05, "text_input_usd_per_mtok": 0.1, "text_output_usd_per_mtok": 0.5}


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def test_route_counters_and_average_latency():
    registry = MetricsRegistry()
    registry.record("/v1/designs", 200, 100.0, {})
    registry.record("/v1/designs", 429, 50.0, {"error_code": "rate_limited"})

    route = registry.snapshot(**PRICES)["routes"]["/v1/designs"]

    assert route == {
        "requests": 2,
        "errors": 1,
        "avg_latency_ms": 75.0,
        "error_codes": {"rate_limited": 1},
    }


def test_images_and_estimated_cost_of_the_day():
    registry = MetricsRegistry()
    registry.record("/v1/designs", 200, 1.0, {"provider": "openai", "images": 2})
    registry.record("/v1/designs", 200, 1.0, {"provider": "fake", "images": 1})
    registry.record(
        "/v1/pricing/suggest", 200, 1.0, {"input_tokens": 1_000_000, "output_tokens": 200_000}
    )

    today = registry.snapshot(**PRICES)["today"]

    assert today["images"] == {"openai": 2, "fake": 1}
    assert today["text_calls"] == 1
    assert today["estimated_cost_usd"] == {"images": 0.1, "text": 0.2, "total": 0.3}


def test_day_counters_reset_at_colombian_midnight():
    clock = Clock(datetime(2026, 11, 19, 4, 59, tzinfo=UTC))  # 23:59 in Colombia
    registry = MetricsRegistry(clock)
    registry.record("/v1/designs", 200, 1.0, {"provider": "openai", "images": 1})

    clock.now += timedelta(minutes=2)
    snapshot = registry.snapshot(**PRICES)

    assert snapshot["today"]["images"] == {}
    assert snapshot["routes"]["/v1/designs"]["requests"] == 1  # route totals are kept


def test_metrics_endpoint_requires_api_key(client):
    response = client.get("/v1/metrics")

    assert response.status_code == 401


def test_metrics_endpoint_reports_traffic(client, auth_headers):
    client.post("/v1/designs", json=PAYLOAD, headers=auth_headers)
    client.post("/v1/designs", json={}, headers=auth_headers)

    body = client.get("/v1/metrics", headers=auth_headers).json()

    designs = body["routes"]["/v1/designs"]
    assert designs["requests"] == 2
    assert designs["errors"] == 1
    assert designs["error_codes"] == {"invalid_request": 1}
    assert body["today"]["images"] == {"fake": 1}
    assert body["today"]["estimated_cost_usd"]["total"] == 0
    assert body["image_budget"] == {
        "daily_image_limit": 30,
        "paid_images_used_today": 0,
        "remaining_today": 30,
    }


def test_metrics_never_expose_keys(client, auth_headers):
    text = client.get("/v1/metrics", headers=auth_headers).text

    assert TEST_API_KEY not in text
