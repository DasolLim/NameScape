"""Guest sessions: a provisional identity, good for one claim.

Internal to accounts, because a guest session is an identity and identity is
what this module owns. It is deliberately not a fifth public function: callers
ask for a claimant, not for a session to be created.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Discovery, GuestSession, User

#: Matches the claim it protects. A cookie that outlived the claim would only
#: promise something the database had already released.
GUEST_TTL_SECONDS: Final = 60 * 60 * 24 * 7


@dataclass(frozen=True, slots=True)
class Guest:
    id: UUID
    cookie: str


def _signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="toponomicon-guest")


def cookie_for(guest_id: UUID) -> str:
    """The signed cookie naming this guest session."""
    return _signer().dumps(str(guest_id))


def identify(cookie: str | None) -> UUID | None:
    """The guest session a cookie names, or None if it names nothing valid."""
    if cookie is None:
        return None
    try:
        raw = _signer().loads(cookie, max_age=GUEST_TTL_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    try:
        return UUID(str(raw))
    except ValueError:
        return None


async def resolve(session: AsyncSession, cookie: str | None) -> Guest:
    """The guest this cookie belongs to, opening a session if there is none.

    A cookie can outlive its row: the session is written in the same
    transaction as the claim, so a claim that rolls back takes the session with
    it. Checking the row exists is what keeps a stale cookie from becoming a
    foreign key violation on the next attempt.
    """
    existing = identify(cookie)
    if (
        cookie is not None
        and existing is not None
        and await session.get(GuestSession, existing) is not None
    ):
        return Guest(id=existing, cookie=cookie)

    guest = GuestSession()
    session.add(guest)
    await session.flush()
    return _issue(guest.id)


def _issue(guest_id: UUID) -> Guest:
    return Guest(id=guest_id, cookie=cookie_for(guest_id))


async def merge(session: AsyncSession, cookie: str | None, user: User) -> int:
    """Give a guest's claim to an account. Returns how many moved.

    Safe to run repeatedly: a session that has already been merged is left
    exactly as it was, including when it was merged. Nothing here can fail a
    sign-in, because a guest cookie is not a credential - a forged one, an
    unknown one and a spent one all mean the same thing, which is no claim.
    """
    guest_id = identify(cookie)
    if guest_id is None:
        return 0

    guest = await session.get(GuestSession, guest_id)
    if guest is None or guest.merged_into is not None:
        return 0

    # Clearing expires_at is what puts the claim out of reach of the expiry
    # job; clearing guest_session_id is what leaves a second run nothing to
    # move. Synchronised so any Discovery already loaded here is not stale.
    moved = (
        (
            await session.execute(
                update(Discovery)
                .where(Discovery.guest_session_id == guest_id)
                .values(
                    claimant_type="user", user_id=user.id, guest_session_id=None, expires_at=None
                )
                .returning(Discovery.id)
                .execution_options(synchronize_session="fetch")
            )
        )
        .scalars()
        .all()
    )
    guest.merged_into = user.id
    guest.merged_at = datetime.now(UTC)
    await session.flush()
    return len(moved)
