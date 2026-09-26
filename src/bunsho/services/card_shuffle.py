"""A shuffle that is random across cards but repeatable for one card.

``next_card`` is stateless and must offer the same card until it is answered, so it cannot draw a
fresh random number on every call. Instead each card gets a rank from a seeded hash of its identity
and last review; picking the lowest rank is a random-looking choice that only changes when the
candidates or the card's own state change.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime

from bunsho.models.review import CardKey


class StableShuffle:
    """Ranks cards in an order that looks random but is the same on every call."""

    def __init__(self, seed: int | None = None) -> None:
        """Create the shuffle.

        Args:
            seed: Fixes the order (tests). Defaults to a random seed, so each process shuffles
                differently.
        """
        self._seed = secrets.randbits(64) if seed is None else seed

    def rank(self, key: CardKey, last_review: datetime | None) -> int:
        """Return the card's position in the shuffle; the lowest rank is offered first.

        Including ``last_review`` reshuffles a card each time it is answered, so the order in which
        cards come back is not the order they were first studied in.

        Args:
            key: The card.
            last_review: When the card was last answered, or ``None`` for a new card.

        Returns:
            A number that is fixed for these arguments and this seed.
        """
        reviewed = "" if last_review is None else last_review.isoformat()
        payload = f"{self._seed}|{key.item_id}|{key.direction.value}|{reviewed}".encode()
        return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest())
