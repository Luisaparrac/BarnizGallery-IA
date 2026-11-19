"""Per-request context: the ``X-Request-ID`` and fields for logs and metrics.

``RequestContextMiddleware`` takes the ``X-Request-ID`` header (or generates one), stores it
in a ``contextvar`` and returns it in the response. Services add safe fields (provider,
model, error code…) with ``set_field``; the values never include keys, prompts or
personal data.
"""

import re
import uuid
from contextvars import ContextVar
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_fields: ContextVar[dict[str, Any] | None] = ContextVar("request_fields", default=None)


def current_request_id() -> str | None:
    return _request_id.get()


def set_field(name: str, value: Any) -> None:
    """Attach a field to the current request (ignored outside a request)."""
    fields = _fields.get()
    if fields is not None:
        fields[name] = value


def current_fields() -> dict[str, Any]:
    return dict(_fields.get() or {})


def resolve_request_id(incoming: str | None) -> str:
    """Reuse a well-formed incoming id; otherwise generate a new one."""
    if incoming and _VALID_REQUEST_ID.match(incoming):
        return incoming
    return uuid.uuid4().hex


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope.get("headers", [])).get(REQUEST_ID_HEADER.lower().encode())
        request_id = resolve_request_id(incoming.decode("latin-1") if incoming else None)
        id_token = _request_id.set(request_id)
        # A mutable dict: code running in FastAPI's thread pool sees and fills the same one.
        fields_token = _fields.set({})

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            _request_id.reset(id_token)
            _fields.reset(fields_token)
