"""`knowvault eval-retrieval`: runs the evaluation in a disposable database."""

import asyncio
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import asyncpg
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

import knowvault
from knowvault.adapters.embeddings import build_embedding_model
from knowvault.adapters.storage.filesystem import FilesystemStorage
from knowvault.core.config import Settings
from knowvault.core.db import Database
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


async def run(settings: Settings, options: EvalOptions) -> Path:
    corpus = sorted(options.corpus_dir.glob("*.md"))
    if not corpus:
        raise SystemExit(f"No Markdown files in {options.corpus_dir}")
    questions = load_dataset(options.dataset)

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
                report = await run_retrieval_eval(
                    settings=eval_settings,
                    database=database,
                    storage=FilesystemStorage(Path(storage_dir)),
                    embeddings=build_embedding_model(eval_settings),
                    corpus=corpus,
                    questions=questions,
                    modes=options.modes,
                    top_k=options.top_k,
                )
        finally:
            await database.dispose()
    finally:
        if not options.keep_database:
            await _admin_execute(url, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')

    options.output_dir.mkdir(parents=True, exist_ok=True)
    report.config["label"] = options.label
    stem = f"{report.created_at:%Y-%m-%d-%H%M}-retrieval"
    if options.label:
        stem += f"-{options.label}"
    (options.output_dir / f"{stem}.json").write_text(to_json(report), encoding="utf-8")
    markdown = options.output_dir / f"{stem}.md"
    markdown.write_text(to_markdown(report), encoding="utf-8")
    return markdown
