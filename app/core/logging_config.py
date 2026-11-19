"""Structured logs: one JSON object per line on stdout (what Render collects).

Every line carries the ``request_id`` of the current request. ``AccessLogMiddleware``
writes one line per request with the route, status, duration and the safe fields that
services attach (provider, model, strategy, error code…).

Never logged: API keys, headers, request bodies, prompts or customer text. Exceptions
are logged with their type and stack frames but *without their message*, because a
validation error message can contain the customer's text.
"""

import json
import logging
import sys
import time
import traceback
from datetime import UTC, datetime
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.request_context import current_fields, current_request_id

_STANDARD_ATTRIBUTES = set(vars(logging.LogRecord("", 0, "", 0, "", (), None)))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRIBUTES and not key.startswith("_"):
                entry[key] = value
        if record.exc_info and record.exc_info[0] is not None:
            entry["exc_type"] = record.exc_info[0].__name__
            entry["stack"] = "".join(traceback.format_tb(record.exc_info[2]))
        return json.dumps(entry, ensure_ascii=False, default=str)


_base_record_factory = logging.getLogRecordFactory()


def _record_with_request_id(*args: Any, **kwargs: Any) -> logging.LogRecord:
    """Stamp the request id when the record is *created* (formatting may happen later)."""
    record = _base_record_factory(*args, **kwargs)
    request_id = current_request_id()
    if request_id:
        record.request_id = request_id
    return record


def setup_logging(level: str = "INFO") -> None:
    """Send every log (ours and uvicorn's) to stdout as JSON."""
    logging.setLogRecordFactory(_record_with_request_id)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    level = level.upper()
    root.setLevel(level if level in {"DEBUG", "INFO", "WARNING", "ERROR"} else "INFO")
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    # AccessLogMiddleware replaces uvicorn's access log (which has no request_id).
    logging.getLogger("uvicorn.access").disabled = True


access_logger = logging.getLogger("app.access")


class AccessLogMiddleware:
    """Logs one JSON line per HTTP request once the response is finished."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status = 500

        async def capture_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture_status)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            access_logger.info(
                "request",
                extra={
                    "method": scope.get("method"),
                    "route": route_of(scope),
                    "status": status,
                    "duration_ms": duration_ms,
                    **current_fields(),
                },
            )


def route_of(scope: Scope) -> str:
    """Route template (``/v1/designs``): never query strings nor path parameter values.

    Only matched routes are logged by path; each path parameter value is replaced by its
    name (``/x/{id}``). Unknown paths are logged as ``<unmatched>``.
    """
    if "route" not in scope:
        return "<unmatched>"
    path = scope.get("path", "")
    for name, value in scope.get("path_params", {}).items():
        path = path.replace(f"/{value}", f"/{{{name}}}")
    return path
