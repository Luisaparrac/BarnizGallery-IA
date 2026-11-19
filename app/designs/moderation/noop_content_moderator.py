"""Moderator that accepts everything (free provider or moderation disabled).

Pattern: **Adapter** (null object), so ``DesignService`` never checks for ``None``.
"""

from app.designs.moderation.content_moderator import ContentModerator
from app.schemas.designs import DesignRequest


class NoopContentModerator(ContentModerator):
    def check(self, request: DesignRequest) -> None:
        return None
