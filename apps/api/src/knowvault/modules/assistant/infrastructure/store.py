"""Conversations in PostgreSQL. Every query is scoped to the owner."""

import base64
import binascii
import itertools
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, column, delete, exists, func, or_, select, table, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knowvault.core import rate_limit
from knowvault.core.errors import AppError, NotFoundError, RateLimitedError
from knowvault.modules.assistant.application.errors import (
    AnswerInProgressError,
    TokenQuotaExceededError,
)
from knowvault.modules.assistant.application.ports import TurnResult, TurnStart
from knowvault.modules.assistant.domain.model import MessageStatus, Turn
from knowvault.modules.assistant.infrastructure.models import (
    Conversation,
    Message,
    MessageCitation,
    RetrievalTraceRecord,
)
from knowvault.modules.identity.models import User
from knowvault.modules.library.models import Collection, Document
from knowvault.modules.retrieval.domain.model import SearchScope

TOKENS_BUCKET = "tokens_daily"
TOKENS_WINDOW = timedelta(days=1)
QUESTIONS_BUCKET = "chat_questions"
QUESTIONS_WINDOW = timedelta(minutes=1)
# An answer still `streaming` after this long belongs to a process that died; it no longer
# blocks new questions.
STALE_STREAM_AFTER = timedelta(minutes=5)
_TITLE_CHARS = 80
# Messages read to build the history; more than enough for the configured turns.
_HISTORY_MESSAGES = 40
# The columns the assistant reads from chunks: whether they still exist, and their position.
_chunks = table("chunks", column("id"), column("ordinal"))


@dataclass(frozen=True)
class CitationView:
    citation: MessageCitation
    # Position of the cited chunk in its document, while the chunk exists.
    chunk_ordinal: int | None


@dataclass(frozen=True)
class MessageWithCitations:
    message: Message
    citations: list[CitationView]


@dataclass(frozen=True)
class ConversationDetail:
    conversation: Conversation
    messages: list[MessageWithCitations]


def scope_of(conversation: Conversation) -> SearchScope:
    collection = conversation.scope.get("collection_id")
    return SearchScope(
        owner_id=conversation.owner_id,
        collection_id=uuid.UUID(collection) if collection else None,
        document_ids=tuple(uuid.UUID(d) for d in conversation.scope.get("document_ids", [])),
    )


def _encode_cursor(conversation: Conversation) -> str:
    raw = f"{conversation.updated_at.isoformat()}|{conversation.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        updated, conversation_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(updated), uuid.UUID(conversation_id)
    except (ValueError, binascii.Error) as exc:
        raise AppError("The cursor is invalid.") from exc


def _history(messages: Sequence[Message], *, turns: int, max_chars: int) -> list[Turn]:
    """Answered questions, oldest first, newest kept within the limits."""
    pairs: list[Turn] = []
    for question, answer in itertools.pairwise(messages):
        if (
            question.role == "user"
            and answer.role == "assistant"
            and answer.status in (MessageStatus.COMPLETE, MessageStatus.REFUSED)
        ):
            pairs.append(Turn(question.content, answer.content))
    kept: list[Turn] = []
    used = 0
    for turn in reversed(pairs[-turns:] if turns else []):
        size = len(turn.question) + len(turn.answer)
        if used + size > max_chars:
            break
        kept.append(turn)
        used += size
    return kept[::-1]


class PostgresConversationStore:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        history_turns: int,
        history_chars: int,
        daily_token_limit: int,
        questions_per_minute: int,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._history_turns = history_turns
        self._history_chars = history_chars
        self._daily_token_limit = daily_token_limit
        self._questions_per_minute = questions_per_minute

    # --- Conversations ---------------------------------------------------------------------

    async def _check_scope(
        self,
        session: AsyncSession,
        owner_id: uuid.UUID,
        collection_id: uuid.UUID | None,
        document_ids: Sequence[uuid.UUID],
    ) -> None:
        if collection_id is not None:
            found = await session.scalar(
                select(Collection.id).where(
                    Collection.id == collection_id, Collection.owner_id == owner_id
                )
            )
            if found is None:
                raise NotFoundError("The collection does not exist.")
        if document_ids:
            found_ids = set(
                await session.scalars(
                    select(Document.id).where(
                        Document.owner_id == owner_id, Document.id.in_(set(document_ids))
                    )
                )
            )
            if found_ids != set(document_ids):
                raise NotFoundError("A document in the scope does not exist.")

    async def create(
        self,
        owner_id: uuid.UUID,
        *,
        title: str,
        collection_id: uuid.UUID | None,
        document_ids: Sequence[uuid.UUID],
    ) -> Conversation:
        async with self._sessionmaker() as session, session.begin():
            await self._check_scope(session, owner_id, collection_id, document_ids)
            conversation = Conversation(
                owner_id=owner_id,
                title=title,
                scope={
                    "collection_id": str(collection_id) if collection_id else None,
                    "document_ids": [str(d) for d in dict.fromkeys(document_ids)],
                },
            )
            session.add(conversation)
            await session.flush()
            await session.refresh(conversation)
            return conversation

    async def list(
        self, owner_id: uuid.UUID, *, limit: int, cursor: str | None
    ) -> tuple[list[Conversation], str | None]:
        query = select(Conversation).where(Conversation.owner_id == owner_id)
        if cursor is not None:
            updated, conversation_id = _decode_cursor(cursor)
            query = query.where(
                or_(
                    Conversation.updated_at < updated,
                    and_(Conversation.updated_at == updated, Conversation.id < conversation_id),
                )
            )
        async with self._sessionmaker() as session:
            rows = list(
                await session.scalars(
                    query.order_by(Conversation.updated_at.desc(), Conversation.id.desc()).limit(
                        limit + 1
                    )
                )
            )
        if len(rows) > limit:
            return rows[:limit], _encode_cursor(rows[limit - 1])
        return rows, None

    async def get(self, owner_id: uuid.UUID, conversation_id: uuid.UUID) -> ConversationDetail:
        async with self._sessionmaker() as session:
            conversation = await session.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id, Conversation.owner_id == owner_id
                )
            )
            if conversation is None:
                raise NotFoundError("The conversation does not exist.")
            messages = list(
                await session.scalars(
                    select(Message)
                    .where(Message.conversation_id == conversation_id)
                    .order_by(Message.seq)
                )
            )
            citations = await session.execute(
                select(MessageCitation, _chunks.c.ordinal)
                .join(Message, Message.id == MessageCitation.message_id)
                .outerjoin(_chunks, _chunks.c.id == MessageCitation.chunk_id)
                .where(Message.conversation_id == conversation_id)
                .order_by(MessageCitation.message_id, MessageCitation.ordinal)
            )
            by_message: dict[uuid.UUID, list[CitationView]] = {}
            for citation, chunk_ordinal in citations:
                by_message.setdefault(citation.message_id, []).append(
                    CitationView(citation, chunk_ordinal)
                )
        return ConversationDetail(
            conversation,
            [MessageWithCitations(m, by_message.get(m.id, [])) for m in messages],
        )

    async def rename(
        self, owner_id: uuid.UUID, conversation_id: uuid.UUID, title: str
    ) -> Conversation:
        async with self._sessionmaker() as session, session.begin():
            conversation = await session.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id, Conversation.owner_id == owner_id
                )
            )
            if conversation is None:
                raise NotFoundError("The conversation does not exist.")
            conversation.title = title
            await session.flush()
            await session.refresh(conversation)
            return conversation

    async def delete(self, owner_id: uuid.UUID, conversation_id: uuid.UUID) -> None:
        async with self._sessionmaker() as session, session.begin():
            deleted = await session.execute(
                delete(Conversation)
                .where(Conversation.id == conversation_id, Conversation.owner_id == owner_id)
                .returning(Conversation.id)
            )
            if deleted.scalar_one_or_none() is None:
                raise NotFoundError("The conversation does not exist.")

    # --- Answering -------------------------------------------------------------------------

    async def start_turn(
        self, *, owner_id: uuid.UUID, conversation_id: uuid.UUID, question: str
    ) -> TurnStart:
        now = datetime.now(UTC)
        async with self._sessionmaker() as session, session.begin():
            # Serialises the turns of one user, so two requests cannot both pass the checks
            # below. FOR NO KEY UPDATE does not block inserts that reference the user.
            await session.execute(
                select(User.id).where(User.id == owner_id).with_for_update(key_share=True)
            )
            conversation = await session.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id, Conversation.owner_id == owner_id
                )
            )
            if conversation is None:
                raise NotFoundError("The conversation does not exist.")

            streaming = await session.scalar(
                select(
                    exists().where(
                        Message.conversation_id == Conversation.id,
                        Conversation.owner_id == owner_id,
                        Message.status == MessageStatus.STREAMING,
                        Message.created_at > now - STALE_STREAM_AFTER,
                    )
                )
            )
            if streaming:
                raise AnswerInProgressError(
                    "Another answer is still being written. Try again when it has finished."
                )

            recent_questions = await rate_limit.current_count(
                session,
                subject=str(owner_id),
                bucket=QUESTIONS_BUCKET,
                window=QUESTIONS_WINDOW,
                now=now,
            )
            if recent_questions >= self._questions_per_minute:
                raise RateLimitedError(
                    "Too many questions in the last minute. Wait a moment and try again.",
                    retry_after_seconds=rate_limit.seconds_until_reset(now, QUESTIONS_WINDOW),
                )

            used = await rate_limit.current_count(
                session, subject=str(owner_id), bucket=TOKENS_BUCKET, window=TOKENS_WINDOW, now=now
            )
            if used >= self._daily_token_limit:
                raise TokenQuotaExceededError(
                    "You have used today's token quota for questions.",
                    retry_after_seconds=rate_limit.seconds_until_reset(now, TOKENS_WINDOW),
                )

            recent = list(
                await session.scalars(
                    select(Message)
                    .where(Message.conversation_id == conversation_id)
                    .order_by(Message.seq.desc())
                    .limit(_HISTORY_MESSAGES)
                )
            )
            history = _history(
                recent[::-1], turns=self._history_turns, max_chars=self._history_chars
            )

            # Counted in this transaction, so refused questions are not counted.
            await rate_limit.increment(
                session,
                subject=str(owner_id),
                bucket=QUESTIONS_BUCKET,
                window=QUESTIONS_WINDOW,
                now=now,
            )
            asked = Message(
                conversation_id=conversation_id,
                role="user",
                content=question,
                status=MessageStatus.COMPLETE,
            )
            answer = Message(
                conversation_id=conversation_id,
                role="assistant",
                content="",
                status=MessageStatus.STREAMING,
            )
            session.add(asked)
            await session.flush()  # the question gets the lower seq
            session.add(answer)
            if not conversation.title:
                conversation.title = " ".join(question.split())[:_TITLE_CHARS]
            conversation.updated_at = func.now()
            await session.flush()
            return TurnStart(
                conversation_id=conversation_id,
                owner_id=owner_id,
                user_message_id=asked.id,
                assistant_message_id=answer.id,
                question=question,
                scope=scope_of(conversation),
                history=history,
            )

    async def finish_turn(self, turn: TurnStart, result: TurnResult) -> None:
        async with self._sessionmaker() as session, session.begin():
            updated = await session.execute(
                update(Message)
                .where(Message.id == turn.assistant_message_id)
                .values(
                    content=result.content,
                    status=result.status,
                    model_id=result.model_id,
                    prompt_tokens=result.usage.input_tokens,
                    completion_tokens=result.usage.output_tokens,
                    latency_ms=result.latency_ms,
                    error_code=result.error_code,
                )
                .returning(Message.id)
            )
            # The conversation may have been deleted while the answer was written; the tokens
            # were spent all the same.
            if updated.scalar_one_or_none() is not None:
                cited = set(result.cited)
                # A document reprocessed or deleted while the answer was written has lost its
                # chunks; its citations keep only the snapshot.
                chunk_ids = {source.passage.chunk_id for source in result.sources}
                document_ids = {source.passage.document_id for source in result.sources}
                live_chunks: set[uuid.UUID] = set()
                if chunk_ids:
                    live_chunks = set(
                        await session.scalars(
                            select(_chunks.c.id).where(_chunks.c.id.in_(chunk_ids))
                        )
                    )
                live_documents: set[uuid.UUID] = set()
                if document_ids:
                    live_documents = set(
                        await session.scalars(
                            select(Document.id).where(Document.id.in_(document_ids))
                        )
                    )
                session.add_all(
                    MessageCitation(
                        message_id=turn.assistant_message_id,
                        ordinal=source.ordinal,
                        cited=source.ordinal in cited,
                        chunk_id=(
                            source.passage.chunk_id
                            if source.passage.chunk_id in live_chunks
                            else None
                        ),
                        document_id=(
                            source.passage.document_id
                            if source.passage.document_id in live_documents
                            else None
                        ),
                        document_title=source.passage.document_title,
                        quoted_text=source.passage.content,
                        page_start=source.passage.page_start,
                        page_end=source.passage.page_end,
                        heading_path=list(source.passage.heading_path),
                    )
                    for source in result.sources
                )
                if result.trace is not None:
                    session.add(
                        RetrievalTraceRecord(
                            message_id=turn.assistant_message_id,
                            query_original=result.trace.query_original,
                            query_rewritten=result.trace.query_rewritten,
                            candidates=result.trace.candidates,
                            selected_chunk_ids=result.trace.selected_chunk_ids,
                            params=result.trace.params,
                        )
                    )
            if result.usage.total:
                await rate_limit.increment(
                    session,
                    subject=str(turn.owner_id),
                    bucket=TOKENS_BUCKET,
                    window=TOKENS_WINDOW,
                    amount=result.usage.total,
                )
