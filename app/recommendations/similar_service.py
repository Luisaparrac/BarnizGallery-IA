"""Finds the works most similar to a given one ("Obras parecidas" in the piece page).

Pattern: **Facade**. The route only calls ``similar``; the service hides the catalog index
and the explanation. Only the candidates the backend sends are considered (available works),
so a sold or hidden piece is never suggested. Ties are broken by id, so the order is stable.
"""

from app.core.errors import ErrorCode, ServiceError
from app.recommendations.catalog_index import CatalogIndex
from app.recommendations.explanation import spanish_list
from app.schemas.similar import SimilarItem, SimilarRequest, SimilarResponse

MAX_TRAITS_IN_EXPLANATION = 3


class SimilarService:
    def __init__(self, catalog: CatalogIndex | None) -> None:
        self._catalog = catalog

    def similar(self, request: SimilarRequest) -> SimilarResponse:
        if self._catalog is None:
            raise ServiceError(
                ErrorCode.FEATURE_DISABLED, "El índice de obras todavía no está disponible."
            )
        reference = self._catalog.artwork(request.artwork.slug)
        if reference is None:
            raise ServiceError(
                ErrorCode.NOT_ENOUGH_DATA,
                f"La obra '{request.artwork.slug}' no está en el índice de obras.",
            )

        items: list[SimilarItem] = []
        seen: set[str] = {reference.slug}
        for candidate in request.candidates:
            if candidate.slug in seen:
                continue
            seen.add(candidate.slug)
            score = self._catalog.similarity(reference.slug, candidate.slug)
            if score is None:
                continue  # not indexed: nothing learned about it
            other = self._catalog.artwork(candidate.slug)
            shared = self._catalog.shared_traits(reference.slug, candidate.slug)
            same_master = other.master == reference.master
            items.append(
                SimilarItem(
                    artwork_id=candidate.artwork_id,
                    slug=candidate.slug,
                    store_id=candidate.store_id,
                    score=round(score, 4),
                    shared_traits=shared,
                    same_master=same_master,
                    explanation=self._explain(
                        reference.title_es, shared, same_master, other.master
                    ),
                )
            )

        items.sort(key=lambda item: (-item.score, item.artwork_id))
        return SimilarResponse(
            artwork_id=request.artwork.artwork_id,
            slug=reference.slug,
            items=items[: request.limit],
        )

    def _explain(self, title: str, shared: list[str], same_master: bool, master: str) -> str:
        if shared:
            traits = spanish_list(shared[:MAX_TRAITS_IN_EXPLANATION])
            sentence = f"Comparte con «{title}»: {traits}."
        else:
            sentence = f"Se parece a «{title}» en su técnica, colores y figuras."
        if same_master:
            sentence += f" También es de {self._catalog.master(master).name}."
        return sentence
