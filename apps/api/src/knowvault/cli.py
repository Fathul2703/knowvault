"""Administrative command line: `knowvault <command>`."""

import argparse
import asyncio
import getpass
import json
import re
import sys
from datetime import timedelta
from pathlib import Path

from knowvault.core.config import Settings, get_settings
from knowvault.core.db import Database
from knowvault.core.errors import NotFoundError
from knowvault.modules.identity.schemas import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from knowvault.modules.identity.service import IdentityService


async def _create_invite(settings: Settings, days: int) -> str:
    database = Database(settings, use_null_pool=True)
    try:
        async with database.sessionmaker() as session:
            return await IdentityService(session, settings).create_invite(ttl=timedelta(days=days))
    finally:
        await database.dispose()


async def _reset_password(settings: Settings, email: str, password: str) -> None:
    database = Database(settings, use_null_pool=True)
    try:
        async with database.sessionmaker() as session:
            await IdentityService(session, settings).reset_password(
                email=email, new_password=password
            )
    finally:
        await database.dispose()


def _prompt_new_password() -> str:
    password = getpass.getpass("New password: ")
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        sys.exit(f"Password must be {PASSWORD_MIN_LENGTH}-{PASSWORD_MAX_LENGTH} characters long.")
    if getpass.getpass("Repeat password: ") != password:
        sys.exit("Passwords do not match.")
    return password


async def _reindex(settings: Settings, *, include_all: bool) -> int:
    from knowvault.adapters.embeddings import build_embedding_model
    from knowvault.modules.library.processing import queue_stale_embeddings

    database = Database(settings, use_null_pool=True)
    try:
        async with database.sessionmaker() as session:
            return await queue_stale_embeddings(
                session,
                embedding_model=build_embedding_model(settings).model_id,
                max_attempts=settings.job_max_attempts,
                include_all=include_all,
            )
    finally:
        await database.dispose()


def _eval_entities(settings: Settings, pairs_path: Path, output_dir: Path) -> str:
    from datetime import UTC, datetime

    from knowvault.adapters.embeddings import build_embedding_model
    from knowvault.evaluation import entities

    embeddings = build_embedding_model(settings)
    pairs = entities.load_pairs(pairs_path)
    threshold = settings.graph_merge_threshold
    scored, rules, sweep = asyncio.run(entities.evaluate(pairs, embeddings, threshold))
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{datetime.now(UTC):%Y-%m-%d-%H%M}-entities"
    model = embeddings.model_id
    (output_dir / f"{stem}.json").write_text(
        entities.to_json(model, threshold, scored, rules), encoding="utf-8"
    )
    markdown = output_dir / f"{stem}.md"
    markdown.write_text(
        entities.to_markdown(model, threshold, scored, rules, sweep), encoding="utf-8"
    )
    return f"Report written to {markdown}"


async def _extract_graph(settings: Settings) -> int:
    from knowvault.modules.graph.infrastructure.store import queue_all_ready

    database = Database(settings, use_null_pool=True)
    try:
        async with database.sessionmaker() as session:
            count = await queue_all_ready(session, max_attempts=settings.job_max_attempts)
            await session.commit()
            return count
    finally:
        await database.dispose()


def _download_model(settings: Settings) -> str:
    """Downloads the configured local models: the embedding model and, if set, the reranker."""
    from knowvault.adapters.embeddings import BgeM3Embeddings
    from knowvault.adapters.reranking import BgeReranker

    lines = []
    if settings.embedding_provider == "bge-m3":
        model = BgeM3Embeddings(
            settings.embedding_cache_dir,
            threads=settings.embedding_threads,
            batch_size=settings.embedding_batch_size,
        )
        lines.append(f"{model.model_id} is ready in {model.download()}")
    if settings.reranker == "bge-reranker-v2-m3":
        reranker = BgeReranker(settings.embedding_cache_dir, threads=settings.embedding_threads)
        lines.append(f"{reranker.model_id} is ready in {reranker.download()}")
    return "\n".join(lines) or "Nothing to download for the configured providers."


def _export_openapi() -> str:
    # Imported lazily so admin commands do not load the whole web stack.
    from knowvault.main import create_app

    # Schema generation never connects to the database; any syntactically valid URL works.
    settings = Settings(database_url="postgresql+asyncpg://openapi@localhost/openapi")
    return json.dumps(create_app(settings).openapi(), indent=2) + "\n"


def _report_label(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", value):
        raise argparse.ArgumentTypeError("use lowercase letters, digits and hyphens (max 40)")
    return value


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="knowvault", description="KnowVault admin commands")
    commands = parser.add_subparsers(dest="command", required=True)

    invite = commands.add_parser("create-invite", help="create a single-use registration invite")
    invite.add_argument("--days", type=int, default=None, help="days until the invite expires")

    reset = commands.add_parser("reset-password", help="set a new password for a user")
    reset.add_argument("email")

    commands.add_parser("export-openapi", help="print the OpenAPI schema as JSON")
    commands.add_parser("worker", help="run the background worker that processes documents")
    commands.add_parser(
        "download-model", help="download the embedding model now instead of on first use"
    )
    reindex = commands.add_parser(
        "reindex", help="queue documents whose embeddings are missing or from another model"
    )
    reindex.add_argument(
        "--all", action="store_true", help="queue every processed document, not only stale ones"
    )
    evaluation = commands.add_parser(
        "eval-retrieval",
        help="measure retrieval quality on a labelled corpus (uses a disposable *_eval database)",
    )
    evaluation.add_argument("--corpus", type=Path, required=True, help="directory of .md files")
    evaluation.add_argument("--dataset", type=Path, required=True, help="questions (.jsonl)")
    evaluation.add_argument("--output-dir", type=Path, required=True, help="where reports go")
    evaluation.add_argument(
        "--modes",
        nargs="+",
        default=["hybrid", "vector", "fulltext"],
        choices=["hybrid", "vector", "fulltext"],
    )
    evaluation.add_argument("--top-k", type=int, default=10)
    evaluation.add_argument(
        "--graph-variants",
        nargs="+",
        default=[],
        choices=["none", "entities", "neighbours"],
        help="also run hybrid search with these graph retrieval settings on the same database",
    )
    evaluation.add_argument(
        "--keep-database", action="store_true", help="keep the *_eval database for inspection"
    )
    evaluation.add_argument(
        "--label", type=_report_label, help="short tag added to the report name, e.g. fulltext-or"
    )

    answers = commands.add_parser(
        "eval-answers",
        help="measure answers (refusals, citations, prompt injection) on a labelled corpus; "
        "uses LLM_PROVIDER and a disposable *_eval database",
    )
    answers.add_argument("--corpus", type=Path, required=True, help="directory of .md files")
    answers.add_argument("--dataset", type=Path, required=True, help="questions (.jsonl)")
    answers.add_argument("--output-dir", type=Path, required=True, help="where reports go")
    answers.add_argument(
        "--review-dir", type=Path, help="write a manual review sheet of sampled answers here"
    )
    answers.add_argument("--review-size", type=int, default=30, help="answers to sample")
    answers.add_argument("--limit", type=int, help="only the first N questions")
    answers.add_argument(
        "--keep-database", action="store_true", help="keep the *_eval database for inspection"
    )
    answers.add_argument(
        "--label", type=_report_label, help="short tag added to the report name, e.g. sonnet"
    )

    commands.add_parser(
        "extract-graph",
        help="queue knowledge graph extraction for every ready document (e.g. after enabling "
        "the graph); the worker builds it",
    )

    entities = commands.add_parser(
        "eval-entities", help="measure entity name matching on labelled pairs of names"
    )
    entities.add_argument("--pairs", type=Path, required=True, help="labelled pairs (.jsonl)")
    entities.add_argument("--output-dir", type=Path, required=True, help="where reports go")

    review = commands.add_parser(
        "eval-review", help="print the totals of a filled-in answer review sheet"
    )
    review.add_argument("sheet", type=Path, help="review sheet (.md)")

    args = parser.parse_args(argv)

    if args.command == "export-openapi":
        sys.stdout.write(_export_openapi())
        return
    if args.command == "eval-review":
        from knowvault.evaluation.review import format_tally, tally_review

        print(format_tally(tally_review(args.sheet.read_text(encoding="utf-8"))))
        return

    settings = get_settings()
    if args.command == "eval-retrieval":
        from knowvault.evaluation.command import EvalOptions
        from knowvault.evaluation.command import run as run_eval
        from knowvault.modules.retrieval.domain.model import SearchMode

        report = asyncio.run(
            run_eval(
                settings,
                EvalOptions(
                    corpus_dir=args.corpus,
                    dataset=args.dataset,
                    output_dir=args.output_dir,
                    modes=tuple(SearchMode(mode) for mode in args.modes),
                    top_k=args.top_k,
                    keep_database=args.keep_database,
                    label=args.label,
                    graph_variants=tuple(args.graph_variants),
                ),
            )
        )
        print(f"Report written to {report}")
    elif args.command == "eval-answers":
        from knowvault.evaluation.command import AnswerEvalOptions, run_answers

        report = asyncio.run(
            run_answers(
                settings,
                AnswerEvalOptions(
                    corpus_dir=args.corpus,
                    dataset=args.dataset,
                    output_dir=args.output_dir,
                    review_dir=args.review_dir,
                    review_size=args.review_size,
                    keep_database=args.keep_database,
                    label=args.label,
                    limit=args.limit,
                ),
            )
        )
        print(f"Report written to {report}")
    elif args.command == "eval-entities":
        print(_eval_entities(settings, args.pairs, args.output_dir))
    elif args.command == "extract-graph":
        if settings.graph_extractor == "none":
            sys.exit("GRAPH_EXTRACTOR is none: enable it first.")
        count = asyncio.run(_extract_graph(settings))
        print(f"Queued graph extraction for {count} document(s). The worker will build it.")
    elif args.command == "download-model":
        print(_download_model(settings))
    elif args.command == "reindex":
        count = asyncio.run(_reindex(settings, include_all=args.all))
        print(f"Queued {count} document(s). The worker will process them.")
    elif args.command == "worker":
        from knowvault.worker import run

        asyncio.run(run(settings))
    elif args.command == "create-invite":
        code = asyncio.run(_create_invite(settings, args.days or settings.invite_ttl_days))
        print(f"Invite code (shown once): {code}")
    elif args.command == "reset-password":
        password = _prompt_new_password()
        try:
            asyncio.run(_reset_password(settings, args.email, password))
        except NotFoundError as exc:
            sys.exit(str(exc))
        print("Password updated. All existing sessions were signed out.")


if __name__ == "__main__":
    main()
