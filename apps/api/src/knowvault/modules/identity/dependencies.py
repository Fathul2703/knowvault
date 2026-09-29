"""Public dependencies other modules use to require an authenticated user."""

from typing import Annotated

from fastapi import Depends, Request

from knowvault.core.db import SessionDep
from knowvault.core.deps import SettingsDep
from knowvault.core.errors import NotAuthenticatedError
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
