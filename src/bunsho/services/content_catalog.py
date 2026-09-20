"""The ordered, level-tagged list of items new cards are chosen from."""

from __future__ import annotations

from bunsho.models.review import CatalogEntry, ItemType
from bunsho.services.content_repository import ContentRepository


class ContentCatalog:
    """Builds ``CatalogEntry`` lists from ``content.db``.

    This is the one place that decides which items are lesson material: unleveled kanji are
    left out (``ContentRepository.catalog`` filters them).
    """

    def __init__(self, repository: ContentRepository) -> None:
        """Create the catalogue.

        Args:
            repository: The content repository to read.
        """
        self._repository = repository

    def entries(self, item_type: ItemType) -> list[CatalogEntry]:
        """Return the entries for ``item_type`` in stable study order.

        Blocking (SQLite); call it through ``asyncio.to_thread`` from async code.
        """
        return [
            CatalogEntry(item_id=item_id, item_type=item_type, level=level, position=position)
            for position, (item_id, level) in enumerate(self._repository.catalog(item_type))
        ]
