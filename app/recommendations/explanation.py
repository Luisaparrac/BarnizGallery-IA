"""Short Spanish explanation for each recommendation, built from its reasons.

Example: "Coincide con lo que te gusta: los colores rojo y verde, la forma bandeja y las
figuras colibri. Está dentro de tu presupuesto."

Codes are shown as received (normalized, without accents); the backend can replace them
with the display names of its tags or catalogs if it wants.
"""

from app.schemas.recommendations import Candidate, Reasons


def _label(code: str) -> str:
    return code.replace("_", " ").replace("-", " ")


def spanish_list(items: list[str]) -> str:
    """``["a"]`` -> ``a``; ``["a", "b", "c"]`` -> ``a, b y c``."""
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} y {items[-1]}"


def explain(
    reasons: Reasons, candidate: Candidate, popular: bool = False, lead: str | None = None
) -> str:
    """``lead`` (from the catalog index) goes first and replaces the generic sentence."""
    matches: list[str] = []
    if reasons.colors:
        noun = "el color" if len(reasons.colors) == 1 else "los colores"
        matches.append(f"{noun} {spanish_list([_label(c) for c in reasons.colors])}")
    if reasons.shape and candidate.shape:
        matches.append(f"la forma {_label(candidate.shape)}")
    if reasons.style and candidate.style:
        matches.append(f"el estilo {_label(candidate.style)}")
    if reasons.motifs:
        noun = "la figura" if len(reasons.motifs) == 1 else "las figuras"
        matches.append(f"{noun} {spanish_list([_label(m) for m in reasons.motifs])}")

    sentences = [lead] if lead else []
    if matches:
        sentences.append(f"Coincide con lo que te gusta: {spanish_list(matches)}.")
    elif lead:
        pass  # the learned sentence already says why; no generic filler
    elif popular:
        sentences.append("Es una de las obras más populares de la galería.")
    else:
        sentences.append("Es una obra distinta que puede ampliar tus gustos.")

    if reasons.budget is True:
        sentences.append("Está dentro de tu presupuesto.")
    elif reasons.budget is False:
        sentences.append("Su precio está por fuera de tu presupuesto.")
    return " ".join(sentences)
