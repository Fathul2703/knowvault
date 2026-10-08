"""The `extract_graph` job: entities and relations of one processed document."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knowvault.core import jobs
from knowvault.modules.graph.application.ports import EntityExtractor, GraphStore

logger = logging.getLogger(__name__)

EXTRACT_GRAPH_JOB = "extract_graph"


class GraphExtraction:
    """Runs after a document is processed; like processing, results for an outdated version of
    the document are discarded."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        store: GraphStore,
        extractor: EntityExtractor,
    ) -> None:
        self._sessions = sessions
        self._store = store
        self._extractor = extractor

    async def process(self, job: jobs.ClaimedJob) -> None:
        document_id = job.resource_id
        version = int(job.payload["content_version"])
        log = {"document_id": str(document_id), "job_id": str(job.id), "attempt": job.attempts}
        try:
            async with self._sessions() as session:
                document = await self._store.load_document(session, document_id, version)
            if document is None:
                logger.info("graph_skipped_stale", extra=log)
                async with self._sessions() as session:
                    await jobs.mark_succeeded(session, job.id)
                    await session.commit()
                return

            # Outside any transaction: a language-model extractor may take a while.
            graphs = await self._extractor.extract(document.chunks)

            async with self._sessions() as session:
                if not await self._store.lock_current(session, document_id, version):
                    logger.info("graph_discarded_stale", extra=log)
                    await jobs.mark_succeeded(session, job.id)
                    await session.commit()
                    return
                counts = await self._store.replace_document_graph(session, document, graphs)
                await jobs.mark_succeeded(session, job.id)
                await session.commit()
            logger.info(
                "graph_extracted",
                extra={
                    **log,
                    "extractor": self._extractor.name,
                    "entities": counts.entities,
                    "mentions": counts.mentions,
                    "relations": counts.relations,
                },
            )
        except Exception as exc:
            logger.exception("graph_extraction_error", extra=log)
            async with self._sessions() as session:
                # After the last attempt the job is marked dead; the document stays usable.
                await jobs.schedule_retry(session, job, repr(exc))
                await session.commit()
