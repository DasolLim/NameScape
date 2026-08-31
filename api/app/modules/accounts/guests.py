"""Guest sessions: a provisional identity, good for one claim.

Internal to accounts, because a guest session is an identity and identity is
what this module owns. It is deliberately not a fifth public function: callers
ask for a claimant, not for a session to be created.
"""

from dataclasses import dataclass
from typing import Final
from uuid import UUID

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import GuestSession

#: Matches the claim it protects. A cookie that outlived the claim would only
#: promise something the database had already released.
GUEST_TTL_SECONDS: Final = 60 * 60 * 24 * 7


@dataclass(frozen=True, slots=True)
class Guest:
    id: UUID
    cookie: str


def _signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="toponomicon-guest")


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
    return Guest(id=guest_id, cookie=_signer().dumps(str(guest_id)))
