"""`knowvault eval-retrieval` and `eval-answers`: evaluations in a disposable database."""

import asyncio
import os
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import asyncpg
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

import knowvault
from knowvault.adapters.chat import build_chat_models
from knowvault.adapters.embeddings import build_embedding_model
from knowvault.adapters.storage.filesystem import FilesystemStorage
from knowvault.core.config import Settings
from knowvault.core.db import Database
from knowvault.evaluation.answer_report import to_json as answers_to_json
from knowvault.evaluation.answer_report import to_markdown as answers_to_markdown
from knowvault.evaluation.answer_report import to_review_sheet
from knowvault.evaluation.answers import review_sample, run_answer_eval
from knowvault.evaluation.dataset import load_dataset
from knowvault.evaluation.report import to_json, to_markdown
from knowvault.evaluation.runner import run_retrieval_eval
from knowvault.modules.retrieval.domain.model import SearchMode

ALEMBIC_INI = Path(knowvault.__file__).resolve().parents[2] / "alembic.ini"


@dataclass(frozen=True)
class EvalOptions:
    corpus_dir: Path
    dataset: Path
    output_dir: Path
    modes: tuple[SearchMode, ...]
    top_k: int
    keep_database: bool
    # Short tag for the report name and title, e.g. "fulltext-or".
    label: str | None = None


def eval_database_url(settings: Settings) -> str:
    """EVAL_DATABASE_URL, or DATABASE_URL with `_eval` appended to the database name."""
    explicit = os.environ.get("EVAL_DATABASE_URL")
    if explicit:
        return explicit
    url = make_url(str(settings.database_url))
    return url.set(database=f"{url.database}_eval").render_as_string(hide_password=False)


async def _admin_execute(url: str, *statements: str) -> None:
    parsed = make_url(url)
    admin = parsed.set(drivername="postgresql", database="postgres").render_as_string(
        hide_password=False
    )
    connection = await asyncpg.connect(admin)
    try:
        for statement in statements:
            await connection.execute(statement)
    finally:
        await connection.close()


def _database_name(url: str) -> str:
    name = make_url(url).database
    if not name or not name.endswith("_eval"):
        raise SystemExit(f"Refusing to use {name!r}: evaluation database names must end in _eval")
    return name


@dataclass(frozen=True)
class EvalEnvironment:
    settings: Settings
    database: Database
    storage: FilesystemStorage


@asynccontextmanager
async def eval_environment(
    settings: Settings, *, keep_database: bool
) -> AsyncIterator[EvalEnvironment]:
    """A freshly migrated *_eval database and temporary file storage, removed afterwards."""
    url = eval_database_url(settings)
    name = _database_name(url)
    await _admin_execute(
        url, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', f'CREATE DATABASE "{name}"'
    )
    try:
        config = Config(str(ALEMBIC_INI))
        config.set_main_option("sqlalchemy.url", url)
        config.attributes["configure_logger"] = False
        await asyncio.to_thread(command.upgrade, config, "head")

        eval_settings = settings.model_copy(update={"database_url": url})
        database = Database(eval_settings, use_null_pool=True)
        try:
            with tempfile.TemporaryDirectory(prefix="knowvault-eval-") as storage_dir:
                yield EvalEnvironment(eval_settings, database, FilesystemStorage(Path(storage_dir)))
        finally:
            await database.dispose()
    finally:
        if not keep_database:
            await _admin_execute(url, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def corpus_files(corpus_dir: Path) -> list[Path]:
    corpus = sorted(corpus_dir.glob("*.md"))
    if not corpus:
        raise SystemExit(f"No Markdown files in {corpus_dir}")
    return corpus


def report_stem(kind: str, created_at: datetime, label: str | None) -> str:
    stem = f"{created_at:%Y-%m-%d-%H%M}-{kind}"
    return f"{stem}-{label}" if label else stem


async def run(settings: Settings, options: EvalOptions) -> Path:
    corpus = corpus_files(options.corpus_dir)
    questions = load_dataset(options.dataset)

    async with eval_environment(settings, keep_database=options.keep_database) as env:
        report = await run_retrieval_eval(
            settings=env.settings,
            database=env.database,
            storage=env.storage,
            embeddings=build_embedding_model(env.settings),
            corpus=corpus,
            questions=questions,
            modes=options.modes,
            top_k=options.top_k,
        )

    options.output_dir.mkdir(parents=True, exist_ok=True)
    report.config["label"] = options.label
    stem = report_stem("retrieval", report.created_at, options.label)
    (options.output_dir / f"{stem}.json").write_text(to_json(report), encoding="utf-8")
    markdown = options.output_dir / f"{stem}.md"
    markdown.write_text(to_markdown(report), encoding="utf-8")
    return markdown


@dataclass(frozen=True)
class AnswerEvalOptions:
    corpus_dir: Path
    dataset: Path
    output_dir: Path
    # Where the manual review sheet goes; None writes no sheet.
    review_dir: Path | None
    review_size: int
    keep_database: bool
    label: str | None = None
    # Only the first N questions, e.g. to try a paid model cheaply.
    limit: int | None = None


async def run_answers(settings: Settings, options: AnswerEvalOptions) -> Path:
    corpus = corpus_files(options.corpus_dir)
    questions = load_dataset(options.dataset)
    if options.limit is not None:
        questions = questions[: options.limit]

    async with eval_environment(settings, keep_database=options.keep_database) as env:
        report = await run_answer_eval(
            settings=env.settings,
            database=env.database,
            storage=env.storage,
            embeddings=build_embedding_model(env.settings),
            models=build_chat_models(env.settings),
            corpus=corpus,
            questions=questions,
        )

    report.config["label"] = options.label
    stem = report_stem("answers", report.created_at, options.label)
    review_file: str | None = None
    sample = review_sample(report.results, options.review_size)
    if options.review_dir is not None and sample:
        options.review_dir.mkdir(parents=True, exist_ok=True)
        sheet = options.review_dir / f"{stem}-review.md"
        sheet.write_text(to_review_sheet(report, sample, f"{stem}.json"), encoding="utf-8")
        review_file = sheet.name

    options.output_dir.mkdir(parents=True, exist_ok=True)
    (options.output_dir / f"{stem}.json").write_text(answers_to_json(report), encoding="utf-8")
    markdown = options.output_dir / f"{stem}.md"
    markdown.write_text(
        answers_to_markdown(report, review_file=review_file, reviewed=len(sample)),
        encoding="utf-8",
    )
    return markdown
