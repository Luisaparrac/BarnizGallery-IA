"""Rejects request bodies larger than ``MAX_REQUEST_BYTES`` with 413.

The size is checked twice: first with the ``Content-Length`` header (cheap, before reading
anything) and then while the body arrives, for clients that send it in chunks.
"""

from collections.abc import Callable

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import ErrorCode, error_response

TOO_LARGE_MESSAGE = "La solicitud es demasiado grande."


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: Callable[[], int]) -> None:
        self.app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = self._max_bytes()
        declared = dict(scope.get("headers", [])).get(b"content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            response = error_response(413, ErrorCode.INVALID_REQUEST, TOO_LARGE_MESSAGE)
            await response(scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # FastAPI re-raises HTTPException while reading the body; the common
                    # error handler turns it into {"code": "invalid_request", ...} with 413.
                    raise StarletteHTTPException(413, TOO_LARGE_MESSAGE)
            return message

        await self.app(scope, limited_receive, send)
