"""Read-only content routes."""

from __future__ import annotations

import asyncio
import sqlite3

from fastapi import APIRouter, Depends

from bunsho.api.deps import ServicesDep, require_user
from bunsho.api.schemas import ContentSummaryResponse

router = APIRouter(prefix="/content", tags=["content"], dependencies=[Depends(require_user)])


@router.get("/summary", response_model=ContentSummaryResponse)
async def content_summary(services: ServicesDep) -> ContentSummaryResponse:
    """Counts and build metadata for ``content.db``; ``built: false`` if absent or unreadable."""
    repo = services.ctx.content_repo
    if repo is None:
        return ContentSummaryResponse(built=False)
    try:
        counts = await asyncio.to_thread(repo.counts)
        meta = await asyncio.to_thread(repo.meta)
    except (sqlite3.Error, OSError) as exc:
        # Keep paths and driver messages out of the response; /health reports the fault.
        services.ctx.logger.warning(
            "content_summary_unreadable error=%s: %s", type(exc).__name__, exc
        )
        return ContentSummaryResponse(built=False)
    return ContentSummaryResponse(
        built=True, kana=counts.kana, kanji=counts.kanji, vocab=counts.vocab, meta=meta
    )
