"""In-memory counters behind ``GET /v1/metrics``.

``AccessLogMiddleware`` feeds every finished request (route, status, duration and the safe
fields set by the services). The registry keeps:

- per route, since the process started: requests, errors and average latency;
- for the current day (Colombia time): images per provider, text tokens and an
  estimated OpenAI cost.

The data lives in memory, so it resets when Render restarts or wakes the service. The
cost is an estimate from the configured prices; the OpenAI dashboard is the real bill.
"""

import threading
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from app.core.timezones import COLOMBIA


@dataclass
class RouteStats:
    requests: int = 0
    errors: int = 0
    total_ms: float = 0.0
    error_codes: dict[str, int] = field(default_factory=lambda: defaultdict(int))


@dataclass
class DayStats:
    day: date
    images: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    text_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class MetricsRegistry:
    def __init__(self, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._clock = clock
        self._started = clock()
        self._routes: dict[str, RouteStats] = defaultdict(RouteStats)
        self._today = DayStats(self._local_day())
        self._lock = threading.Lock()

    def _local_day(self) -> date:
        return self._clock().astimezone(COLOMBIA).date()

    def _roll_day(self) -> None:
        today = self._local_day()
        if self._today.day != today:
            self._today = DayStats(today)

    def record(self, route: str, status: int, duration_ms: float, fields: dict[str, Any]) -> None:
        with self._lock:
            self._roll_day()
            stats = self._routes[route]
            stats.requests += 1
            stats.total_ms += duration_ms
            if status >= 400:
                stats.errors += 1
                stats.error_codes[str(fields.get("error_code", status))] += 1

            images = fields.get("images")
            if isinstance(images, int) and images > 0:
                self._today.images[str(fields.get("provider", "unknown"))] += images
            tokens_in, tokens_out = fields.get("input_tokens"), fields.get("output_tokens")
            if isinstance(tokens_in, int) or isinstance(tokens_out, int):
                self._today.text_calls += 1
                self._today.input_tokens += tokens_in if isinstance(tokens_in, int) else 0
                self._today.output_tokens += tokens_out if isinstance(tokens_out, int) else 0

    def snapshot(
        self,
        image_cost_usd: float,
        text_input_usd_per_mtok: float,
        text_output_usd_per_mtok: float,
    ) -> dict[str, Any]:
        with self._lock:
            self._roll_day()
            routes = {
                route: {
                    "requests": stats.requests,
                    "errors": stats.errors,
                    "avg_latency_ms": round(stats.total_ms / stats.requests, 1),
                    "error_codes": dict(stats.error_codes),
                }
                for route, stats in sorted(self._routes.items())
            }
            today = self._today
            paid_images = today.images.get("openai", 0)
            image_cost = paid_images * image_cost_usd
            text_cost = (
                today.input_tokens * text_input_usd_per_mtok
                + today.output_tokens * text_output_usd_per_mtok
            ) / 1_000_000
            return {
                "since": self._started.isoformat(timespec="seconds"),
                "routes": routes,
                "today": {
                    "date": today.day.isoformat(),
                    "images": dict(today.images),
                    "text_calls": today.text_calls,
                    "input_tokens": today.input_tokens,
                    "output_tokens": today.output_tokens,
                    "estimated_cost_usd": {
                        "images": round(image_cost, 4),
                        "text": round(text_cost, 6),
                        "total": round(image_cost + text_cost, 4),
                    },
                },
            }
