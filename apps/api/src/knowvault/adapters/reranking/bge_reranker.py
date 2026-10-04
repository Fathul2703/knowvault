"""BAAI/bge-reranker-v2-m3, a multilingual cross-encoder, run locally with ONNX Runtime.

Uses the int8 ONNX export published by the onnx-community organisation (the model is
Apache-2.0), pinned to a revision and downloaded into a plain directory, as for bge-m3 (ADR
0005). Scores are the model's logits passed through a sigmoid, so they lie in [0, 1].
"""

import asyncio
import logging
import math
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastembed.rerank.cross_encoder import TextCrossEncoder

logger = logging.getLogger(__name__)

MODEL_REPO = "onnx-community/bge-reranker-v2-m3-ONNX"
MODEL_REVISION = "6f5ff65298512715a1e669753bc754d2bc8f367b"
MODEL_FILE = "onnx/model_int8.onnx"
MODEL_FILES = (
    "config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    MODEL_FILE,
)
MODEL_ID = f"BAAI/bge-reranker-v2-m3:int8@{MODEL_REVISION[:7]}"
_FASTEMBED_NAME = "knowvault/bge-reranker-v2-m3-int8"
_registration_lock = threading.Lock()
_registered = False


def _register_with_fastembed() -> None:
    global _registered
    from fastembed.common.model_description import ModelSource
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    with _registration_lock:
        if _registered:
            return
        TextCrossEncoder.add_custom_model(
            model=_FASTEMBED_NAME,
            sources=ModelSource(hf=MODEL_REPO),
            model_file=MODEL_FILE,
            description="BAAI/bge-reranker-v2-m3, int8",
            license="apache-2.0",
            size_in_gb=0.57,
        )
        _registered = True


def _sigmoid(logit: float) -> float:
    return 1 / (1 + math.exp(-logit))


class BgeReranker:
    def __init__(self, cache_dir: Path, *, threads: int | None, batch_size: int = 8) -> None:
        self._model_dir = cache_dir / f"bge-reranker-v2-m3-int8-{MODEL_REVISION[:12]}"
        self._threads = threads
        self._batch_size = batch_size
        self._model: TextCrossEncoder | None = None
        self._load_lock = threading.Lock()

    @property
    def model_id(self) -> str:
        return MODEL_ID

    def download(self) -> Path:
        """Fetches the model files if they are not present yet. Safe to call repeatedly."""
        if all((self._model_dir / name).is_file() for name in MODEL_FILES):
            return self._model_dir
        from huggingface_hub import snapshot_download

        logger.info("reranker_download_started", extra={"repo": MODEL_REPO})
        snapshot_download(
            repo_id=MODEL_REPO,
            revision=MODEL_REVISION,
            allow_patterns=list(MODEL_FILES),
            local_dir=self._model_dir,
        )
        logger.info("reranker_download_finished", extra={"path": str(self._model_dir)})
        return self._model_dir

    def _load(self) -> "TextCrossEncoder":
        with self._load_lock:
            if self._model is None:
                from fastembed.rerank.cross_encoder import TextCrossEncoder

                _register_with_fastembed()
                self._model = TextCrossEncoder(
                    model_name=_FASTEMBED_NAME,
                    specific_model_path=str(self.download()),
                    threads=self._threads,
                )
                logger.info("reranker_loaded", extra={"model": MODEL_ID})
            return self._model

    def _score(self, query: str, passages: list[str]) -> list[float]:
        model = self._load()
        logits = list(model.rerank(query, passages, batch_size=self._batch_size))
        if len(logits) != len(passages):
            raise RuntimeError("reranker returned an unexpected number of scores")
        return [_sigmoid(float(logit)) for logit in logits]

    async def score(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        # Inference is CPU-bound; keep the event loop responsive.
        return await asyncio.to_thread(self._score, query, passages)
