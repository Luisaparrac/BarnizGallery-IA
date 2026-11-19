"""Camera compositions used when several images are requested at once.

With ``count > 1`` each image gets a different composition, so the customer sees the
piece from several angles instead of near-duplicates.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Composition:
    code: str
    prompt: str


COMPOSITIONS: tuple[Composition, ...] = (
    Composition(
        "top",
        "Composition: top-down view of the whole piece, seen from directly above, centered.",
    ),
    Composition(
        "three_quarter",
        "Composition: three-quarter view of the whole piece, showing its depth, its edge and "
        "the glossy finish.",
    ),
    Composition(
        "detail",
        "Composition: close-up detail of the decorative motifs, showing the thin layered resin "
        "sheets and their crisp cut edges.",
    ),
)


def compositions_for(count: int) -> list[Composition | None]:
    """One composition per image; a single image keeps the default framing."""
    if count <= 1:
        return [None]
    return [COMPOSITIONS[index % len(COMPOSITIONS)] for index in range(count)]
