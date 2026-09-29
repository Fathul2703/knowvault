"""Administrative command line: `knowvault <command>`."""

import argparse
import asyncio
import getpass
import json
import sys
from datetime import timedelta

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


def _download_model(settings: Settings) -> str:
    from knowvault.adapters.embeddings import BgeM3Embeddings

    if settings.embedding_provider != "bge-m3":
        return f"Nothing to download for EMBEDDING_PROVIDER={settings.embedding_provider}."
    model = BgeM3Embeddings(
        settings.embedding_cache_dir,
        threads=settings.embedding_threads,
        batch_size=settings.embedding_batch_size,
    )
    return f"{model.model_id} is ready in {model.download()}"


def _export_openapi() -> str:
    # Imported lazily so admin commands do not load the whole web stack.
    from knowvault.main import create_app

    # Schema generation never connects to the database; any syntactically valid URL works.
    settings = Settings(database_url="postgresql+asyncpg://openapi@localhost/openapi")
    return json.dumps(create_app(settings).openapi(), indent=2) + "\n"


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

    args = parser.parse_args(argv)

    if args.command == "export-openapi":
        sys.stdout.write(_export_openapi())
        return

    settings = get_settings()
    if args.command == "download-model":
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
