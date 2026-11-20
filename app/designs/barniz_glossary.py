"""Small glossary of Barniz de Pasto, built from the museum's real artworks.

The vocabulary comes from the 21 pieces of the MUSEO collection (shapes, figures and
descriptions in the frontend's ``data/obras.csv``). Each entry explains a Spanish term in
English, so the image model draws the piece the way Pasto masters make it: a "bargueño" is
a colonial writing cabinet, the "Sol de los Pastos" is an eight-pointed solar star, etc.

Lookup is accent- and case-insensitive (``"Bargueño"`` = ``"bargueno"``) and accepts the
Spanish catalog codes, common synonyms and some English words.
"""

import re
from dataclasses import dataclass

from app.core.text import normalize_code


@dataclass(frozen=True)
class GlossaryEntry:
    term: str
    description: str
    #: Normalized words or phrases that point to this entry.
    aliases: tuple[str, ...]


SHAPES: tuple[GlossaryEntry, ...] = (
    GlossaryEntry(
        "bargueño",
        "a colonial bargueño writing cabinet with a drop-front lid, small drawers and "
        "compartments, every surface covered in resin decoration",
        ("bargueno", "barguenos", "cabinet", "escritorio"),
    ),
    GlossaryEntry(
        "jarrón",
        "a turned wooden vase (tall and flared, ovoid or lidded) whose resin decoration "
        "wraps all around its body",
        ("jarron", "florero", "vase"),
    ),
    GlossaryEntry(
        "plato",
        "a round turned wooden plate whose centre holds the main design, framed by "
        "concentric decorative borders",
        ("plato", "platos", "plate"),
    ),
    GlossaryEntry(
        "bandeja",
        "a shallow wooden tray with a raised rim and the decoration on its inner surface",
        ("bandeja", "tray"),
    ),
    GlossaryEntry(
        "máscara",
        "a carved wooden mask with stylized features, headdress and ear ornaments",
        ("mascara", "mask"),
    ),
    GlossaryEntry(
        "cuadro",
        "a carved wooden wall panel, flat or in relief, with the scene filling the whole "
        "surface",
        ("cuadro", "panel", "relieve", "relief"),
    ),
    GlossaryEntry(
        "banco",
        "a low wooden stool with a round seat on a tapered base or curved legs, decorated "
        "on the seat and on every side",
        ("banco", "taburete", "stool"),
    ),
    GlossaryEntry(
        "escultura",
        "a carved wooden figure, such as an animal, fully covered in resin decoration",
        ("escultura", "figura tallada", "talla", "sculpture"),
    ),
    GlossaryEntry(
        "caja",
        "a wooden box or chest with a lid, decorated on the lid and every side",
        ("caja", "cofre", "joyero", "box", "chest"),
    ),
    GlossaryEntry(
        "totuma",
        "a round bowl (totuma or cuenco) decorated inside and out",
        ("totuma", "cuenco", "bowl"),
    ),
)

MOTIFS: tuple[GlossaryEntry, ...] = (
    GlossaryEntry(
        "Sol de los Pastos",
        "the eight-pointed Sun of the Pastos, the pre-Columbian solar star of the Pastos "
        "people, with spirals around it",
        ("sol de los pastos", "sol de pastos", "sun of the pastos"),
    ),
    GlossaryEntry(
        "precolombino",
        "pre-Columbian Pasto designs: stepped frets, spirals, checkerboards and stylized "
        "animals",
        ("precolombino", "precolombina", "precolombinos", "precolombinas", "pre-columbian"),
    ),
    GlossaryEntry(
        "grecas",
        "stepped Andean fret borders",
        ("greca", "grecas", "fret", "frets"),
    ),
    GlossaryEntry(
        "flora",
        "dense Pasto flora: stylized flowers, leaves and vines covering the surface",
        ("flora", "floral", "flor", "flores", "rosas", "hojas", "flowers"),
    ),
    GlossaryEntry(
        "geométrico",
        "geometric patterns: frets, zigzags and checkerboards in flat colours",
        ("geometrico", "geometricos", "geometrica", "geometric", "ajedrezado", "ajedrezados"),
    ),
    GlossaryEntry(
        "paisaje de Nariño",
        "an Andean Nariño landscape with green hills, villages, stone walls and crops",
        ("paisaje", "paisaje andino", "landscape", "narino"),
    ),
    GlossaryEntry(
        "Galeras",
        "the Galeras volcano that rises over Pasto",
        ("galeras", "volcan"),
    ),
    GlossaryEntry(
        "figura humana",
        "human figures and faces in the regional style, often indigenous elders with "
        "feathered headdresses",
        # No family words ("abuela", "taita"): in a title they usually name who receives the
        # gift ("Bandeja para mi abuela"), not a figure to paint.
        ("antropomorfo", "rostro", "rostros", "retrato", "retratos", "indigena"),
    ),
    GlossaryEntry(
        "zoomorfo",
        "stylized Andean animals and birds",
        ("zoomorfo", "animales", "aves", "animals", "birds"),
    ),
    GlossaryEntry(
        "colibrí",
        "stylized hummingbirds with long beaks and open wings",
        ("colibri", "colibries", "hummingbird", "hummingbirds"),
    ),
    GlossaryEntry(
        "papagayo",
        "parrots and macaws with layered colourful plumage",
        ("papagayo", "papagayos", "guacamaya", "guacamayas", "loro", "parrot", "macaw"),
    ),
    GlossaryEntry(
        "jaguar",
        "a jaguar with spotted fur among leaves",
        ("jaguar",),
    ),
    GlossaryEntry(
        "toro",
        "a bull in a charging pose",
        ("toro", "bull"),
    ),
)

STYLES: dict[str, str] = {
    "tradicional": "traditional Pasto style: dense, symmetrical decoration with fine "
    "filigree lines",
    "contemporaneo": "contemporary style: bold flat colour fields and modern compositions",
    "fusion": "fusion style: pre-Columbian symbols combined with contemporary portraits "
    "or natural wood",
}

TECHNIQUE = (
    "Technique: mopa-mopa resin is boiled, kneaded and stretched by hand into very thin "
    "coloured films, then cut with a blade and laid over the carved wood in layers."
)


def _contains(text: str, alias: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", text) is not None


class BarnizGlossary:
    """Finds the glossary entries mentioned in a piece of text."""

    @staticmethod
    def find(text: str, entries: tuple[GlossaryEntry, ...]) -> list[GlossaryEntry]:
        normalized = normalize_code(text)
        return [
            entry
            for entry in entries
            if any(_contains(normalized, alias) for alias in entry.aliases)
        ]

    @classmethod
    def shape(cls, text: str) -> GlossaryEntry | None:
        found = cls.find(text, SHAPES)
        return found[0] if found else None

    @classmethod
    def motifs(cls, text: str) -> list[GlossaryEntry]:
        return cls.find(text, MOTIFS)

    @staticmethod
    def style(text: str) -> str | None:
        return STYLES.get(normalize_code(text))
