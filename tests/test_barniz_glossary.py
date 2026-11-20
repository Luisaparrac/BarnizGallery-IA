import pytest

from app.designs.barniz_glossary import MOTIFS, SHAPES, STYLES, BarnizGlossary

# Shape, motif and style codes used by the museum's real pieces (frontend data/obras.csv,
# 21 works, November 2026). Every one of them must be described by the glossary.
MUSEUM_SHAPES = ["mueble", "jarron", "cuadro", "mascara", "plato", "escultura", "banco"]
MUSEUM_MOTIFS = ["floral", "geometrico", "paisaje", "antropomorfo", "precolombino", "zoomorfo"]
MUSEUM_STYLES = ["tradicional", "contemporaneo", "fusion"]
PROPER_NOUNS = ("bargueño", "Nariño")
# Names of real pieces whose words the glossary should recognise.
MUSEUM_TITLES = {
    "Bargueño Colonial": "bargueño",
    "Jarrón Flora Azul": "jarrón",
    "Plato Decorado": "plato",
    "Máscara Músico": "máscara",
    "Cuadro Mujer y Tradición": "cuadro",
}


@pytest.mark.parametrize(("title", "term"), MUSEUM_TITLES.items())
def test_recognises_real_piece_names(title, term):
    assert BarnizGlossary.shape(title).term == term


@pytest.mark.parametrize("shape", [s for s in MUSEUM_SHAPES if s != "mueble"])
def test_every_museum_shape_code_has_an_entry(shape):
    assert BarnizGlossary.shape(shape) is not None


def test_generic_furniture_is_not_assumed_to_be_a_bargueno():
    assert BarnizGlossary.shape("mueble") is None
    assert BarnizGlossary.shape("Bargueño de cuatro gavetas").term == "bargueño"


@pytest.mark.parametrize("motif", MUSEUM_MOTIFS)
def test_every_museum_motif_code_has_an_entry(motif):
    assert BarnizGlossary.motifs(motif)


@pytest.mark.parametrize("style", MUSEUM_STYLES)
def test_every_museum_style_has_a_description(style):
    assert BarnizGlossary.style(style)


def test_style_lookup_ignores_accents_and_case():
    assert BarnizGlossary.style("Contemporáneo") == STYLES["contemporaneo"]
    assert BarnizGlossary.style("barroco") is None


def test_sol_de_los_pastos_is_explained():
    [entry] = [
        e for e in BarnizGlossary.motifs("Plato con el Sol de los Pastos") if "Sun" in e.description
    ]

    assert "eight-pointed" in entry.description


def test_finds_several_motifs_in_a_description():
    text = "Banco con un jaguar y un colibrí en los costados y figuras precolombinas"

    terms = {entry.term for entry in BarnizGlossary.motifs(text)}

    assert {"jaguar", "colibrí", "precolombino"} <= terms


def test_matching_ignores_accents_case_and_language():
    assert BarnizGlossary.motifs("COLIBRÍ")[0].term == "colibrí"
    assert BarnizGlossary.motifs("hummingbirds")[0].term == "colibrí"
    assert BarnizGlossary.shape("Vase").term == "jarrón"


def test_only_whole_words_match():
    # Aliases match whole words only: "historia" has no motif, "platonico" is not "plato".
    assert not BarnizGlossary.motifs("historia")
    assert BarnizGlossary.shape("platonico") is None


def test_unknown_text_has_no_entries():
    assert BarnizGlossary.motifs("algo sin relación") == []
    assert BarnizGlossary.shape("objeto raro") is None


def test_entries_are_english_and_unique():
    for entry in (*SHAPES, *MOTIFS):
        # English text; only Spanish proper nouns keep their accents.
        text = entry.description
        for proper_noun in PROPER_NOUNS:
            text = text.replace(proper_noun, "")
        assert text.isascii(), entry.term
    assert len({entry.term for entry in SHAPES}) == len(SHAPES)
    assert len({entry.term for entry in MOTIFS}) == len(MOTIFS)
