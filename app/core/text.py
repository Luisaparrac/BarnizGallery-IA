"""Small text helpers shared by several areas."""

import unicodedata


def normalize_code(value: str) -> str:
    """Return a comparable code: lowercase, trimmed, without accents.

    ``"Colibrí "`` and ``"colibri"`` both become ``"colibri"``.
    """
    decomposed = unicodedata.normalize("NFKD", value.strip().lower())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(without_accents.split())
