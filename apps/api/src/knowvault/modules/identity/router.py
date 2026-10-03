"""HTTP endpoints for authentication."""

import logging
from typing import Annotated

from fastapi import APIRouter, Header, Request, Response, status

from knowvault.core.config import Settings
from knowvault.core.deps import ClientAddressDep, SettingsDep, StorageDep
from knowvault.core.errors import Problem
from knowvault.modules.identity.dependencies import CurrentUser, IdentityServiceDep
from knowvault.modules.identity.schemas import (
    AccountDeletion,
    LoginRequest,
    RegisterRequest,
    UserOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

UserAgent = Annotated[str | None, Header(include_in_schema=False)]

_ERRORS: dict[int | str, dict[str, object]] = {
    code: {"model": Problem, "content": {"application/problem+json": {}}}
    for code in (400, 401, 403, 409, 415, 422, 429)
}


def _set_session_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_absolute_ttl_days * 24 * 3600,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserOut,
    responses=_ERRORS,
)
async def register(
    body: RegisterRequest,
    response: Response,
    service: IdentityServiceDep,
    settings: SettingsDep,
    client_address: ClientAddressDep,
    user_agent: UserAgent = None,
) -> UserOut:
    """Creates an account from a single-use invite code and signs the user in."""
    result = await service.register(
        invite_code=body.invite_code,
        email=body.email,
        display_name=body.display_name,
        password=body.password,
        user_agent=user_agent,
        client_address=client_address,
    )
    _set_session_cookie(response, settings, result.session_token)
    return UserOut.model_validate(result.user)


@router.post("/login", response_model=UserOut, responses=_ERRORS)
async def login(
    body: LoginRequest,
    response: Response,
    service: IdentityServiceDep,
    settings: SettingsDep,
    client_address: ClientAddressDep,
    user_agent: UserAgent = None,
) -> UserOut:
    """Signs the user in and sets the session cookie."""
    result = await service.login(
        email=body.email,
        password=body.password,
        user_agent=user_agent,
        client_address=client_address,
    )
    _set_session_cookie(response, settings, result.session_token)
    return UserOut.model_validate(result.user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def logout(request: Request, service: IdentityServiceDep, settings: SettingsDep) -> Response:
    """Revokes the current session. Succeeds even if the session is already invalid."""
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        await service.logout(token)
    return _signed_out(settings)


def _signed_out(settings: Settings) -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/me", response_model=UserOut, responses=_ERRORS)
async def me(user: CurrentUser) -> UserOut:
    """Returns the signed-in user."""
    return UserOut.model_validate(user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def delete_account(
    body: AccountDeletion,
    user: CurrentUser,
    service: IdentityServiceDep,
    settings: SettingsDep,
    storage: StorageDep,
) -> Response:
    """Deletes the account and all its data: documents and their files, notes, collections,
    conversations and sessions. Requires the current password. Cannot be undone."""
    keys = await service.delete_account(user, password=body.password)
    failed = 0
    for key in keys:
        try:
            await storage.delete(key)
        except OSError:
            failed += 1
    if failed:
        # The database is the source of truth; orphaned files are only wasted space.
        logger.warning("account_files_not_deleted", extra={"count": failed})
    return _signed_out(settings)
