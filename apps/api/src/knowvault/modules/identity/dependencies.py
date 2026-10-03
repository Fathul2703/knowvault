"""Public dependencies other modules use to require an authenticated user."""

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Annotated, Any

from fastapi import Depends, Request

from knowvault.core import rate_limit
from knowvault.core.config import Settings
from knowvault.core.db import SessionDep
from knowvault.core.deps import SettingsDep
from knowvault.core.errors import NotAuthenticatedError, RateLimitedError
from knowvault.modules.identity.models import User
from knowvault.modules.identity.service import IdentityService


def get_identity_service(session: SessionDep, settings: SettingsDep) -> IdentityService:
    return IdentityService(session, settings)


IdentityServiceDep = Annotated[IdentityService, Depends(get_identity_service)]


async def get_current_user(
    request: Request, service: IdentityServiceDep, settings: SettingsDep
) -> User:
    token = request.cookies.get(settings.session_cookie_name)
    user = await service.resolve_session(token) if token else None
    if user is None:
        raise NotAuthenticatedError
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def user_rate_limit(
    bucket: str, limit: Callable[[Settings], int], window: timedelta, detail: str
) -> Any:
    """A dependency that allows each user `limit(settings)` requests per fixed `window`.

    Counters live in PostgreSQL (`core.rate_limit`), so limits hold across API processes.
    """

    async def check(user: CurrentUser, session: SessionDep, settings: SettingsDep) -> None:
        count = await rate_limit.increment(
            session, subject=str(user.id), bucket=bucket, window=window
        )
        await session.commit()
        if count > limit(settings):
            raise RateLimitedError(
                detail, retry_after_seconds=rate_limit.seconds_until_reset_now(window)
            )

    dependency: Callable[..., Awaitable[None]] = check
    return Depends(dependency)
