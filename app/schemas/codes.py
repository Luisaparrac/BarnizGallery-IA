"""Catalog codes shared by recommendations and pricing.

The backend sends text codes (``"rojo"``, ``"colibri"``, ``"bandeja"``) instead of ids,
so the service works with today's text tags and with the future catalogs. Codes are
normalized, so ``"Colibrí"`` and ``"colibri"`` are the same code.
"""

from typing import Annotated

from pydantic import AfterValidator, Field, StringConstraints

from app.core.text import normalize_code

Code = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=60),
    AfterValidator(normalize_code),
]
CodeList = Annotated[list[Code], Field(default_factory=list, max_length=50)]
Currency = Annotated[
    str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z]{3}$")
]

#: Artwork or master slug, exactly as in the museum catalog index (``bargueno-colonial``):
#: lowercase letters and digits separated by single hyphens.
Slug = Annotated[str, StringConstraints(max_length=120, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]
