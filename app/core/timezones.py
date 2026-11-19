"""Time zone used for "today" (daily image limit and daily metrics)."""

from datetime import timedelta, timezone

#: Colombia is UTC-5 all year (no daylight saving time), so a fixed offset is exact.
COLOMBIA = timezone(timedelta(hours=-5), "America/Bogota")
