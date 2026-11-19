"""Daily limit of paid images, to protect the OpenAI balance.

Images are *reserved* before calling the provider and *released* if the call fails, so a
failed generation does not consume the quota. The day follows Colombia's time zone
(UTC-5, no daylight saving time). The counter lives in memory: it resets if the service
restarts, so the OpenAI project should also have a spending limit.
"""

import math
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from app.core.errors import ErrorCode, ServiceError
from app.core.timezones import COLOMBIA


class DailyImageBudget:
    def __init__(self, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._clock = clock
        self._day: date | None = None
        self._used = 0
        self._lock = threading.Lock()

    def _today(self) -> datetime:
        return self._clock().astimezone(COLOMBIA)

    def _roll_day(self, now: datetime) -> None:
        if self._day != now.date():
            self._day = now.date()
            self._used = 0

    def used_today(self) -> int:
        with self._lock:
            self._roll_day(self._today())
            return self._used

    def reserve(self, count: int, limit: int) -> None:
        """Reserve ``count`` images or raise 429 ``budget_exceeded``."""
        with self._lock:
            now = self._today()
            self._roll_day(now)
            if self._used + count > limit:
                midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
                wait = math.ceil((midnight.replace(tzinfo=COLOMBIA) - now).total_seconds())
                raise ServiceError(
                    ErrorCode.BUDGET_EXCEEDED,
                    f"Se alcanzó el límite diario de {limit} imágenes. Intenta de nuevo mañana.",
                    headers={"Retry-After": str(max(1, wait))},
                )
            self._used += count

    def release(self, count: int) -> None:
        """Give back images that were reserved but not generated."""
        with self._lock:
            self._used = max(0, self._used - count)
