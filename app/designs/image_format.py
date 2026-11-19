"""Image formats the service can return and their MIME types."""

from typing import Literal

ImageFormat = Literal["webp", "jpeg", "png"]

MIME_TYPES: dict[str, str] = {
    "webp": "image/webp",
    "jpeg": "image/jpeg",
    "png": "image/png",
}
