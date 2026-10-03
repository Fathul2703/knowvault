"""Hybrid search for answers, in its own short-lived session."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knowvault.modules.retrieval.application.search import SearchService
from knowvault.modules.retrieval.domain.model import SearchHit, SearchMode, SearchScope


class SearchRetriever:
    def __init__(
        self, sessionmaker: async_sessionmaker[AsyncSession], search: SearchService
    ) -> None:
        self._sessionmaker = sessionmaker
        self._search = search

    async def retrieve(self, query: str, *, scope: SearchScope, top_k: int) -> list[SearchHit]:
        # The connection returns to the pool as soon as the search is done, before the model
        # starts writing (docs/ARCHITECTURE.md §10.2).
        async with self._sessionmaker() as session:
            result = await self._search.search(
                session, query=query, scope=scope, top_k=top_k, mode=SearchMode.HYBRID
            )
        return result.hits
