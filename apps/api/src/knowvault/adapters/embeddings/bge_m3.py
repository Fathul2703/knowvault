"""BAAI/bge-m3 dense embeddings, run locally with ONNX Runtime through fastembed.

Uses the int8-quantised ONNX export (Xenova/bge-m3, MIT licence) — see ADR 0005 for the
measurements behind that choice. The files are downloaded once, at a pinned revision, into a
plain directory (not the Hugging Face symlink cache: ONNX Runtime refuses external data that
resolves outside the model directory).
"""

import asyncio
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from knowvault.core.embeddings import EMBEDDING_DIMENSIONS

if TYPE_CHECKING:
    from fastembed import TextEmbedding

logger = logging.getLogger(__name__)

MODEL_REPO = "Xenova/bge-m3"
MODEL_REVISION = "4de13258303883538bd53b696b452bf8099f0858"
MODEL_FILE = "onnx/model_int8.onnx"
MODEL_FILES = (
    "config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    MODEL_FILE,
)
MODEL_ID = f"BAAI/bge-m3:int8@{MODEL_REVISION[:7]}"
_FASTEMBED_NAME = "knowvault/bge-m3-int8"
_registration_lock = threading.Lock()
_registered = False


def _register_with_fastembed() -> None:
    global _registered
    from fastembed import TextEmbedding
    from fastembed.common.model_description import ModelSource, PoolingType

    with _registration_lock:
        if _registered:
            return
        # bge-m3 dense vectors are the normalised [CLS] token embedding.
        TextEmbedding.add_custom_model(
            model=_FASTEMBED_NAME,
            pooling=PoolingType.CLS,
            normalization=True,
            sources=ModelSource(hf=MODEL_REPO),
            dim=EMBEDDING_DIMENSIONS,
            model_file=MODEL_FILE,
            description="BAAI/bge-m3, int8",
            license="mit",
        )
        _registered = True


class BgeM3Embeddings:
    def __init__(self, cache_dir: Path, *, threads: int | None, batch_size: int) -> None:
        self._model_dir = cache_dir / f"bge-m3-int8-{MODEL_REVISION[:12]}"
        self._threads = threads
        self._batch_size = batch_size
        self._model: TextEmbedding | None = None
        self._load_lock = threading.Lock()

    @property
    def model_id(self) -> str:
        return MODEL_ID

    @property
    def dimensions(self) -> int:
        return EMBEDDING_DIMENSIONS

    def download(self) -> Path:
        """Fetches the model files if they are not present yet. Safe to call repeatedly."""
        if all((self._model_dir / name).is_file() for name in MODEL_FILES):
            return self._model_dir
        from huggingface_hub import snapshot_download

        logger.info("embedding_model_download_started", extra={"repo": MODEL_REPO})
        snapshot_download(
            repo_id=MODEL_REPO,
            revision=MODEL_REVISION,
            allow_patterns=list(MODEL_FILES),
            local_dir=self._model_dir,
        )
        logger.info("embedding_model_download_finished", extra={"path": str(self._model_dir)})
        return self._model_dir

    def _load(self) -> "TextEmbedding":
        with self._load_lock:
            if self._model is None:
                from fastembed import TextEmbedding

                _register_with_fastembed()
                self._model = TextEmbedding(
                    model_name=_FASTEMBED_NAME,
                    specific_model_path=str(self.download()),
                    threads=self._threads,
                )
                logger.info("embedding_model_loaded", extra={"model": MODEL_ID})
            return self._model

    def _check(self, vectors: list[list[float]], expected: int) -> list[list[float]]:
        if len(vectors) != expected or any(len(v) != EMBEDDING_DIMENSIONS for v in vectors):
            raise RuntimeError("embedding model returned vectors of an unexpected shape")
        return vectors

    def _embed_documents(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        vectors = [v.tolist() for v in model.embed(texts, batch_size=self._batch_size)]
        return self._check(vectors, len(texts))

    def _embed_query(self, text: str) -> list[float]:
        model = self._load()
        return self._check([v.tolist() for v in model.query_embed(text)], 1)[0]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # Inference is CPU-bound; keep the event loop responsive.
        return await asyncio.to_thread(self._embed_documents, texts)

    async def embed_query(self, text: str) -> list[float]:
        return await asyncio.to_thread(self._embed_query, text)
