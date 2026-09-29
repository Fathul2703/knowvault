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

    args = parser.parse_args(argv)

    if args.command == "export-openapi":
        sys.stdout.write(_export_openapi())
        return

    settings = get_settings()
    if args.command == "worker":
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
