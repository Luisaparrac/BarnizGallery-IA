"""Builds the English prompt sent to the image provider.

Pattern: **Builder**. The prompt is assembled step by step (craft, object, style, colours,
motifs, size, customer notes, composition, photography, restrictions) through chainable
``with_*`` methods, and ``build`` joins the parts in a fixed order. ``for_request`` acts as
the director: it applies every step needed for a ``DesignRequest``. The fixed parts (craft
description, photography and restrictions) are always included, even if a caller forgets
a step.

The optional ``with_craft_glossary`` step uses ``BarnizGlossary`` (vocabulary of the
museum's real pieces) to explain, in English, the technique, the shape ("bargueño" is a
colonial writing cabinet), the style and up to ``MAX_MOTIF_NOTES`` figures found in the
motifs, title and description ("Sol de los Pastos", "grecas", "colibrí"...).
"""

import re
from typing import Self

from app.designs.barniz_glossary import TECHNIQUE, BarnizGlossary, GlossaryEntry
from app.designs.compositions import Composition
from app.schemas.designs import DesignColor, DesignRequest

CRAFT = (
    "A single handcrafted piece of Barniz de Pasto (Mopa-Mopa varnish) from Pasto, Colombia: "
    "very thin sheets of coloured natural resin, hand-cut and applied over carved wood, "
    "forming flat, crisp, layered shapes with a glossy lacquered finish."
)
DEFAULT_FRAMING = "Centered product photograph of the whole piece."
PHOTOGRAPHY = (
    "Product photograph on a plain neutral cream background, soft diffuse studio lighting, "
    "sharp focus, realistic materials."
)
RESTRICTIONS = "No people, no hands, no text, no letters, no watermarks and no logos."
#: Glossary notes about figures are capped so the prompt stays focused.
MAX_MOTIF_NOTES = 4


def _clean(text: str) -> str:
    """Collapse whitespace and drop quotes so customer text cannot break the prompt."""
    return re.sub(r"\s+", " ", text.replace('"', "'")).strip()


class DesignPromptBuilder:
    def __init__(self) -> None:
        self._object: str | None = None
        self._style: str | None = None
        self._colors: list[DesignColor] = []
        self._motifs: list[str] = []
        self._size_notes: str | None = None
        self._title: str | None = None
        self._description: str | None = None
        self._customer_language = "es"
        self._composition: Composition | None = None
        self._glossary = False

    @classmethod
    def for_request(cls, request: DesignRequest, composition: Composition | None = None) -> str:
        """Director: build the full prompt for a design request (and one composition)."""
        return (
            cls()
            .with_object(request.shape)
            .with_style(request.style)
            .with_colors(request.colors)
            .with_motifs(request.motifs)
            .with_size_notes(request.size_notes)
            .with_customer_notes(request.title, request.description, request.language)
            .with_composition(composition)
            .with_craft_glossary()
            .build()
        )

    def with_object(self, shape: str) -> Self:
        self._object = _clean(shape)
        return self

    def with_style(self, style: str) -> Self:
        self._style = _clean(style)
        return self

    def with_colors(self, colors: list[DesignColor]) -> Self:
        self._colors = list(colors)
        return self

    def with_motifs(self, motifs: list[str]) -> Self:
        self._motifs = [_clean(motif) for motif in motifs if motif.strip()]
        return self

    def with_size_notes(self, size_notes: str | None) -> Self:
        self._size_notes = _clean(size_notes) if size_notes else None
        return self

    def with_customer_notes(self, title: str, description: str, language: str = "es") -> Self:
        self._title = _clean(title) or None
        self._description = _clean(description) or None
        self._customer_language = language
        return self

    def with_composition(self, composition: Composition | None) -> Self:
        self._composition = composition
        return self

    def with_craft_glossary(self, enabled: bool = True) -> Self:
        """Explain the technique, shape, style and figures with the Barniz glossary."""
        self._glossary = enabled
        return self

    def _shape_entry(self) -> GlossaryEntry | None:
        if not self._glossary:
            return None
        # The shape field first; the title helps when the shape is generic ("mueble").
        return BarnizGlossary.shape(self._object or "") or BarnizGlossary.shape(self._title or "")

    def _motif_entries(self) -> list[GlossaryEntry]:
        if not self._glossary:
            return []
        found: list[GlossaryEntry] = []
        sources = ("; ".join(self._motifs), self._title or "", self._description or "")
        for source in sources:
            for entry in BarnizGlossary.motifs(source):
                if entry not in found:
                    found.append(entry)
        return found[:MAX_MOTIF_NOTES]

    def build(self) -> str:
        parts = [CRAFT]
        if self._glossary:
            parts.append(TECHNIQUE)
        if self._object:
            shape = self._shape_entry()
            detail = f": {shape.description}" if shape else ""
            parts.append(f'Object: a "{self._object}" made in this technique{detail}.')
        if self._style:
            style = BarnizGlossary.style(self._style) if self._glossary else None
            parts.append(f'Style: "{self._style}"' + (f", {style}." if style else "."))
        if self._colors:
            palette = ", ".join(f"{color.name} ({color.hex.upper()})" for color in self._colors)
            parts.append(f"Main resin colours: {palette}.")
        if self._motifs:
            parts.append(f"Decorative motifs: {', '.join(self._motifs)}.")
        notes = self._motif_entries()
        if notes:
            explained = "; ".join(f"{entry.term} = {entry.description}" for entry in notes)
            parts.append(f"Barniz de Pasto references: {explained}.")
        if self._size_notes:
            parts.append(f'Approximate size: "{self._size_notes}".')
        if self._title or self._description:
            language = "Spanish" if self._customer_language == "es" else "English"
            notes = " - ".join(text for text in (self._title, self._description) if text)
            parts.append(f'Customer request (written in {language}): "{notes}".')
        parts.append(self._composition.prompt if self._composition else DEFAULT_FRAMING)
        parts.append(PHOTOGRAPHY)
        parts.append(RESTRICTIONS)
        return " ".join(parts)
