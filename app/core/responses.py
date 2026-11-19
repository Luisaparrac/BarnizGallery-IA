"""JSON response that declares its charset explicitly."""

from fastapi.responses import JSONResponse


class Utf8JSONResponse(JSONResponse):
    """JSON sent as UTF-8 and declared as such, so accents and ñ reach any client intact.

    FastAPI already encodes JSON as UTF-8 but sends ``application/json`` without a charset;
    some HTTP clients then fall back to ISO-8859-1. This removes the ambiguity.
    """

    media_type = "application/json; charset=utf-8"
