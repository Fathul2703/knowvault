"""The evaluation runner end to end on a tiny corpus with fake embeddings."""

import json
from pathlib import Path

from knowvault.adapters.embeddings import FakeEmbeddings
from knowvault.adapters.storage.filesystem import FilesystemStorage
from knowvault.core.config import Settings
from knowvault.core.db import Database
from knowvault.evaluation.dataset import Question
from knowvault.evaluation.report import to_json, to_markdown
from knowvault.evaluation.runner import run_retrieval_eval
from knowvault.modules.retrieval.domain.model import SearchMode


# Keyword-style queries: full-text search requires every query word (AND), so these test the
# runner's mechanics rather than how well natural-language questions are matched.
def storage_root(storage: FilesystemStorage) -> Path:
    return storage._root


QUESTIONS = [
    Question("q1", "ERR_4711 storage cluster", "en", "identifier", "runbook.md",
             ("storage cluster timed out",)),
    Question("q2", "invoices kept ten years", "en", "lexical", "policy.md",
             ("kept for ten years",)),
    Question("q3", "How do I bake bread?", "en", "unanswerable", None, ()),
]  # fmt: skip


async def test_runs_every_question_in_every_mode(
    tmp_path: Path, settings: Settings, database: Database
) -> None:
    # A storage location different from settings.storage_dir, as in `knowvault eval-retrieval`:
    # the worker must read from the storage the corpus was uploaded to.
    storage = FilesystemStorage(tmp_path / "eval-storage")
    assert storage_root(storage) != settings.storage_dir.resolve()
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "runbook.md").write_text(
        "# Runbook\n\nERR_4711 means the connection to the storage cluster timed out."
    )
    (corpus / "policy.md").write_text("# Retention\n\nInvoices are kept for ten years.")

    report = await run_retrieval_eval(
        settings=settings,
        database=database,
        storage=storage,
        embeddings=FakeEmbeddings(),
        corpus=sorted(corpus.glob("*.md")),
        questions=QUESTIONS,
        top_k=5,
    )

    assert report.config["documents"] == 2
    assert report.config["chunks"] == 2
    assert report.config["answerable_questions"] == 2
    assert [s.mode for s in report.summaries] == ["hybrid", "vector", "fulltext"]
    assert len(report.results) == 3 * len(QUESTIONS)

    by_key = {(r.mode, r.question_id): r for r in report.results}
    # The error code is matched exactly by full-text search and ranked first in hybrid.
    assert by_key[("fulltext", "q1")].rank == 1
    assert by_key[("hybrid", "q1")].rank == 1
    assert by_key[("hybrid", "q3")].rank is None
    hybrid = report.summaries[0]
    assert hybrid.questions == 2
    assert hybrid.success[10] == 1.0
    assert set(hybrid.by_category) == {"identifier", "lexical"}
    assert report.similarity["unanswerable_top"], "unanswerable similarity is recorded"

    markdown = to_markdown(report)
    assert "| hybrid (RRF) | 100.0% |" in markdown
    assert "## Misses" in markdown
    payload = json.loads(to_json(report))
    assert payload["config"]["embedding_model"] == "fake-bow"
    assert len(payload["results"]) == 9


async def test_restricts_modes(
    tmp_path: Path, settings: Settings, database: Database, storage: FilesystemStorage
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "policy.md").write_text("Invoices are kept for ten years.")
    report = await run_retrieval_eval(
        settings=settings,
        database=database,
        storage=storage,
        embeddings=FakeEmbeddings(),
        corpus=[corpus / "policy.md"],
        questions=[QUESTIONS[1]],
        modes=(SearchMode.FULLTEXT,),
    )
    assert [s.mode for s in report.summaries] == ["fulltext"]
    assert report.results[0].rank == 1
