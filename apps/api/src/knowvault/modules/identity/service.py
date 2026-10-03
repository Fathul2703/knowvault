"""Identity use cases: invites, registration, login, sessions and password resets."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import column, delete, select, table, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from knowvault.core import rate_limit
from knowvault.core.config import Settings
from knowvault.core.errors import AppError, ConflictError, NotFoundError, RateLimitedError
from knowvault.modules.identity.credentials import (
    hash_password,
    hash_token,
    new_token,
    password_needs_rehash,
    verify_password,
)
from knowvault.modules.identity.models import Invite, User, UserSession

logger = logging.getLogger(__name__)

LOGIN_FAILURE_BUCKET = "login_failure"
LOGIN_IP_FAILURE_BUCKET = "login_failure_ip"
REGISTER_IP_BUCKET = "register_ip"
REGISTER_IP_WINDOW = timedelta(hours=1)
# Only the columns account deletion needs; identity does not depend on the library module.
_documents = table("documents", column("owner_id"), column("storage_key"))
_usage_counters = table("usage_counters", column("subject"))
# Avoid a database write on every request just to track activity.
LAST_SEEN_RESOLUTION = timedelta(minutes=5)


class InvalidCredentialsError(AppError):
    status_code = 401
    code = "invalid_credentials"
    title = "Invalid email or password"


class InvalidPasswordError(AppError):
    status_code = 403
    code = "invalid_password"
    title = "The password is not correct"


class InvalidInviteError(AppError):
    status_code = 400
    code = "invalid_invite"
    title = "Invite code is invalid, expired or already used"


class EmailTakenError(ConflictError):
    code = "email_taken"
    title = "An account with this email already exists"


@dataclass(frozen=True)
class LoginResult:
    user: User
    session_token: str


def _now() -> datetime:
    return datetime.now(UTC)


def _truncate(value: str | None, length: int) -> str | None:
    return value[:length] if value else None


class IdentityService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._db = session
        self._settings = settings

    # --- Invites -------------------------------------------------------------------------

    async def create_invite(self, *, ttl: timedelta | None = None) -> str:
        """Creates a single-use invite and returns its code. The code is not stored."""
        code = new_token()
        ttl = ttl or timedelta(days=self._settings.invite_ttl_days)
        self._db.add(Invite(code_hash=hash_token(code), expires_at=_now() + ttl))
        await self._db.commit()
        return code

    # --- Registration & login ------------------------------------------------------------

    async def register(
        self,
        *,
        invite_code: str,
        email: str,
        display_name: str,
        password: str,
        user_agent: str | None,
        client_address: str | None = None,
    ) -> LoginResult:
        now = _now()
        if client_address is not None:
            # Every attempt counts, so invite codes cannot be guessed from one address.
            attempts = await rate_limit.increment(
                self._db,
                subject=f"ip:{client_address}",
                bucket=REGISTER_IP_BUCKET,
                window=REGISTER_IP_WINDOW,
            )
            await self._db.commit()
            if attempts > self._settings.register_ip_max_attempts:
                raise RateLimitedError(
                    "Too many registration attempts. Try again later.",
                    retry_after_seconds=rate_limit.seconds_until_reset(now, REGISTER_IP_WINDOW),
                )
        invite = await self._db.scalar(
            select(Invite).where(Invite.code_hash == hash_token(invite_code)).with_for_update()
        )
        if invite is None or invite.used_at is not None or invite.expires_at <= now:
            raise InvalidInviteError

        user = User(email=email, display_name=display_name, password_hash=hash_password(password))
        self._db.add(user)
        try:
            await self._db.flush()
        except IntegrityError as exc:
            await self._db.rollback()
            raise EmailTakenError from exc

        invite.used_at = now
        invite.used_by = user.id
        token = self._add_session(user, user_agent, now)
        await self._db.commit()
        logger.info("user_registered", extra={"user_id": str(user.id)})
        return LoginResult(user=user, session_token=token)

    async def login(
        self,
        *,
        email: str,
        password: str,
        user_agent: str | None,
        client_address: str | None = None,
    ) -> LoginResult:
        window = timedelta(minutes=self._settings.login_window_minutes)
        # Failures are limited per email (guessing one password) and per client address
        # (trying many accounts).
        limits = [(f"email:{email}", LOGIN_FAILURE_BUCKET, self._settings.login_max_attempts)]
        if client_address is not None:
            limits.append(
                (
                    f"ip:{client_address}",
                    LOGIN_IP_FAILURE_BUCKET,
                    self._settings.login_ip_max_attempts,
                )
            )
        for subject, bucket, limit in limits:
            failures = await rate_limit.current_count(
                self._db, subject=subject, bucket=bucket, window=window
            )
            if failures >= limit:
                raise RateLimitedError(
                    "Too many failed login attempts. Try again later.",
                    retry_after_seconds=rate_limit.seconds_until_reset(_now(), window),
                )

        user = await self._db.scalar(select(User).where(User.email == email))
        password_ok = verify_password(user.password_hash if user else None, password)
        if user is None or not password_ok or not user.is_active:
            for subject, bucket, _ in limits:
                await rate_limit.increment(self._db, subject=subject, bucket=bucket, window=window)
            await self._db.commit()
            raise InvalidCredentialsError

        if password_needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        token = self._add_session(user, user_agent, _now())
        await self._db.commit()
        return LoginResult(user=user, session_token=token)

    async def delete_account(self, user: User, *, password: str) -> list[str]:
        """Deletes the user and everything they own; returns the storage keys of their files.

        Documents, chunks, notes, collections, conversations and sessions go with the user
        (ON DELETE CASCADE). Files are removed by the caller after the commit. Wrong passwords
        count as failed logins, so this cannot be used to guess the password.
        """
        window = timedelta(minutes=self._settings.login_window_minutes)
        subject = f"email:{user.email}"
        failures = await rate_limit.current_count(
            self._db, subject=subject, bucket=LOGIN_FAILURE_BUCKET, window=window
        )
        if failures >= self._settings.login_max_attempts:
            raise RateLimitedError(
                "Too many failed attempts. Try again later.",
                retry_after_seconds=rate_limit.seconds_until_reset(_now(), window),
            )
        if not verify_password(user.password_hash, password):
            await rate_limit.increment(
                self._db, subject=subject, bucket=LOGIN_FAILURE_BUCKET, window=window
            )
            await self._db.commit()
            raise InvalidPasswordError

        user_id = user.id
        keys: list[str] = list(
            await self._db.scalars(
                select(_documents.c.storage_key).where(
                    _documents.c.owner_id == user_id, _documents.c.storage_key.is_not(None)
                )
            )
        )
        await self._db.execute(
            delete(_usage_counters).where(_usage_counters.c.subject.in_([str(user_id), subject]))
        )
        await self._db.execute(delete(User).where(User.id == user_id))
        await self._db.commit()
        logger.info("account_deleted", extra={"user_id": str(user_id)})
        return keys

    # --- Sessions ------------------------------------------------------------------------

    def _add_session(self, user: User, user_agent: str | None, now: datetime) -> str:
        token = new_token()
        self._db.add(
            UserSession(
                user_id=user.id,
                token_hash=hash_token(token),
                user_agent=_truncate(user_agent, 255),
                last_seen_at=now,
                expires_at=now + timedelta(days=self._settings.session_absolute_ttl_days),
            )
        )
        return token

    async def resolve_session(self, token: str) -> User | None:
        """Returns the active user for a session token, or None if the session is not valid."""
        now = _now()
        row = (
            await self._db.execute(
                select(UserSession, User)
                .join(User, User.id == UserSession.user_id)
                .where(UserSession.token_hash == hash_token(token))
            )
        ).one_or_none()
        if row is None:
            return None
        user_session, user = row
        idle_deadline = user_session.last_seen_at + timedelta(
            hours=self._settings.session_idle_ttl_hours
        )
        if (
            user_session.revoked_at is not None
            or user_session.expires_at <= now
            or idle_deadline <= now
            or not user.is_active
        ):
            return None
        if now - user_session.last_seen_at >= LAST_SEEN_RESOLUTION:
            user_session.last_seen_at = now
            await self._db.commit()
        return user

    async def logout(self, token: str) -> None:
        await self._db.execute(
            update(UserSession)
            .where(UserSession.token_hash == hash_token(token), UserSession.revoked_at.is_(None))
            .values(revoked_at=_now())
        )
        await self._db.commit()

    # --- Administration ------------------------------------------------------------------

    async def reset_password(self, *, email: str, new_password: str) -> None:
        """Sets a new password and revokes every existing session of the user."""
        user = await self._db.scalar(select(User).where(User.email == email.lower()))
        if user is None:
            raise NotFoundError(f"No user with email {email!r}")
        user.password_hash = hash_password(new_password)
        await self._db.execute(
            update(UserSession)
            .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
            .values(revoked_at=_now())
        )
        await self._db.commit()
        logger.info("password_reset", extra={"user_id": str(user.id)})
