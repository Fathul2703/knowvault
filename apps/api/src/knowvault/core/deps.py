"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, Request

from knowvault.core.chat import ChatModels
from knowvault.core.config import Settings
from knowvault.core.embeddings import EmbeddingModel
from knowvault.core.net import client_address
from knowvault.core.reranker import Reranker
from knowvault.core.storage import ObjectStorage


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def get_storage(request: Request) -> ObjectStorage:
    storage: ObjectStorage = request.app.state.storage
    return storage


StorageDep = Annotated[ObjectStorage, Depends(get_storage)]


def get_embeddings(request: Request) -> EmbeddingModel:
    embeddings: EmbeddingModel = request.app.state.embeddings
    return embeddings


EmbeddingsDep = Annotated[EmbeddingModel, Depends(get_embeddings)]


def get_chat_models(request: Request) -> ChatModels:
    models: ChatModels = request.app.state.chat_models
    return models


ChatModelsDep = Annotated[ChatModels, Depends(get_chat_models)]


def get_client_address(request: Request, settings: SettingsDep) -> str:
    return client_address(request, settings.trusted_proxy_networks)


ClientAddressDep = Annotated[str, Depends(get_client_address)]


def get_reranker(request: Request) -> Reranker | None:
    reranker: Reranker | None = request.app.state.reranker
    return reranker


RerankerDep = Annotated[Reranker | None, Depends(get_reranker)]
