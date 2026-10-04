"""HTTP endpoints for conversations and streamed, cited answers."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse

from knowvault.core.db import Database, SessionDep, get_database
from knowvault.core.deps import ChatModelsDep, EmbeddingsDep, RerankerDep, SettingsDep
from knowvault.core.errors import Problem
from knowvault.modules.assistant.api import sse
from knowvault.modules.assistant.api.schemas import (
    CitationOut,
    ConversationCreate,
    ConversationDetailOut,
    ConversationOut,
    ConversationPage,
    ConversationScope,
    ConversationUpdate,
    MessageCreate,
    MessageOut,
)
from knowvault.modules.assistant.application.answer import AnswerService, AnswerSettings
from knowvault.modules.assistant.infrastructure.models import Conversation
from knowvault.modules.assistant.infrastructure.retriever import SearchRetriever
from knowvault.modules.assistant.infrastructure.store import (
    MessageWithCitations,
    PostgresConversationStore,
)
from knowvault.modules.identity.dependencies import CurrentUser
from knowvault.modules.retrieval.application.search import SearchService
from knowvault.modules.retrieval.infrastructure.postgres_index import PostgresChunkIndex

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])

_ERRORS: dict[int | str, dict[str, object]] = {
    code: {"model": Problem, "content": {"application/problem+json": {}}}
    for code in (400, 401, 403, 404, 415, 422)
}

_SSE_DESCRIPTION = """\
A stream of Server-Sent Events:

- `message.created`: `{conversation_id, user_message_id, message_id}`
- `sources`: `{sources: [{ordinal, chunk_id, chunk_ordinal, document_id, title, page_start,
  page_end, heading_path, quoted_text}]}`, sent before the first token
- `token`: `{text}`, repeated
- `done`: `{message_id, status, citations, invalid_citations, usage}`; when `status` is
  `refused`, show the standard refusal text (also sent as tokens) instead of anything streamed
- `error`: `{message_id, code, detail}`, instead of `done`

Render `[n]` as a link only when `n` is in `citations`.
"""


def get_store(
    settings: SettingsDep, database: Annotated[Database, Depends(get_database)]
) -> PostgresConversationStore:
    return PostgresConversationStore(
        database.sessionmaker,
        history_turns=settings.chat_history_turns,
        history_chars=settings.chat_history_chars,
        daily_token_limit=settings.chat_daily_token_limit,
        questions_per_minute=settings.chat_questions_per_minute,
    )


Store = Annotated[PostgresConversationStore, Depends(get_store)]


def get_answer_service(
    settings: SettingsDep,
    database: Annotated[Database, Depends(get_database)],
    store: Store,
    embeddings: EmbeddingsDep,
    reranker: RerankerDep,
    models: ChatModelsDep,
) -> AnswerService:
    search = SearchService(
        embeddings, PostgresChunkIndex(), reranker, rerank_candidates=settings.rerank_candidates
    )
    retriever = SearchRetriever(database.sessionmaker, search)
    return AnswerService(
        store,
        retriever,
        models,
        AnswerSettings(
            max_sources=settings.chat_max_sources,
            context_chars=settings.chat_context_chars,
            max_output_tokens=settings.chat_max_output_tokens,
        ),
    )


def _conversation_out(conversation: Conversation) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        title=conversation.title,
        scope=ConversationScope.model_validate(conversation.scope),
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _message_out(item: MessageWithCitations) -> MessageOut:
    message = item.message
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        status=message.status,
        model_id=message.model_id,
        error_code=message.error_code,
        created_at=message.created_at,
        citations=[
            CitationOut(
                ordinal=view.citation.ordinal,
                cited=view.citation.cited,
                chunk_id=view.citation.chunk_id,
                chunk_ordinal=view.chunk_ordinal,
                document_id=view.citation.document_id,
                document_title=view.citation.document_title,
                quoted_text=view.citation.quoted_text,
                page_start=view.citation.page_start,
                page_end=view.citation.page_end,
                heading_path=list(view.citation.heading_path),
            )
            for view in item.citations
        ],
    )


@router.get("", response_model=ConversationPage, responses=_ERRORS)
async def list_conversations(
    user: CurrentUser,
    store: Store,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> ConversationPage:
    """The user's conversations, most recently active first."""
    items, next_cursor = await store.list(user.id, limit=limit, cursor=cursor)
    return ConversationPage(items=[_conversation_out(c) for c in items], next_cursor=next_cursor)


@router.post(
    "", response_model=ConversationOut, status_code=status.HTTP_201_CREATED, responses=_ERRORS
)
async def create_conversation(
    body: ConversationCreate, user: CurrentUser, store: Store
) -> ConversationOut:
    conversation = await store.create(
        user.id,
        title=body.title,
        collection_id=body.scope.collection_id,
        document_ids=body.scope.document_ids,
    )
    return _conversation_out(conversation)


@router.get("/{conversation_id}", response_model=ConversationDetailOut, responses=_ERRORS)
async def get_conversation(
    conversation_id: uuid.UUID, user: CurrentUser, store: Store
) -> ConversationDetailOut:
    """The conversation with every message and the sources of each answer."""
    detail = await store.get(user.id, conversation_id)
    return ConversationDetailOut(
        **_conversation_out(detail.conversation).model_dump(),
        messages=[_message_out(m) for m in detail.messages],
    )


@router.patch("/{conversation_id}", response_model=ConversationOut, responses=_ERRORS)
async def update_conversation(
    conversation_id: uuid.UUID, body: ConversationUpdate, user: CurrentUser, store: Store
) -> ConversationOut:
    return _conversation_out(await store.rename(user.id, conversation_id, body.title))


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def delete_conversation(
    conversation_id: uuid.UUID, user: CurrentUser, store: Store
) -> Response:
    await store.delete(user.id, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{conversation_id}/messages",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": _SSE_DESCRIPTION,
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
        **{
            code: {"model": Problem, "content": {"application/problem+json": {}}}
            for code in (401, 403, 404, 409, 415, 422, 429)
        },
    },
)
async def ask(
    conversation_id: uuid.UUID,
    body: MessageCreate,
    user: CurrentUser,
    session: SessionDep,
    service: Annotated[AnswerService, Depends(get_answer_service)],
) -> StreamingResponse:
    """Asks a question; the answer streams back as Server-Sent Events.

    Answers use only the conversation's documents and cite them as `[n]`. When the documents
    do not answer the question, the answer is refused rather than guessed. Errors found
    before streaming starts (unknown conversation, an answer already in progress, a spent
    daily token quota) are ordinary problem responses.
    """
    # The request's session (used to authenticate) would otherwise keep its connection until
    # the response ends; the answer service opens short sessions of its own.
    await session.close()
    turn = await service.start(
        owner_id=user.id, conversation_id=conversation_id, question=body.content
    )
    return sse.EventStreamResponse(service.stream(turn))
