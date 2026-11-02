"""What every router shares: dependencies, cookies, path types, error docs."""

from typing import Annotated, Any, Final

from fastapi import Cookie, Depends, HTTPException, Path, Response
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_redis
from app.db import get_session
from app.models import User
from app.modules import accounts, discoveries
from app.modules.accounts import guests

SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]

SESSION_COOKIE: Final = "namescape_session"
#: A guest's provisional identity. Separate from the session cookie so signing
#: in never has to think about clearing it.
GUEST_COOKIE: Final = "namescape_guest"

SessionCookie = Annotated[str | None, Cookie(alias=SESSION_COOKIE)]
GuestCookie = Annotated[str | None, Cookie(alias=GUEST_COOKIE)]

#: Postgres bigint. A larger id is a bad request, not a lookup that misses.
MAX_BIGINT: Final = 2**63 - 1
PlaceId = Annotated[int, Path(ge=1, le=MAX_BIGINT)]


class ErrorResponse(BaseModel):
    detail: str


_DESCRIBED: Final = {
    400: "Malformed request body",
    401: "Not signed in",
    403: "Not allowed",
    404: "Not found",
    409: "Conflict",
    422: "Refused",
    428: "An etymology is required first",
    429: "Too many requests",
    503: "Writes are temporarily unavailable",
}

#: Every write passes the rate limiter, which can refuse or be unavailable,
#: and a body that is not JSON at all is a 400 rather than a 422.
WRITE_ERRORS: Final = (400, 429, 503)


def errors(*codes: int) -> dict[int | str, dict[str, Any]]:
    """Declare the failures a route can actually produce.

    Contract fuzzing treats an undocumented status code as a defect, and it is
    right to: a client generated from this schema would not know to handle it.
    """
    return {code: {"model": ErrorResponse, "description": _DESCRIBED[code]} for code in codes}


async def viewer(session: AsyncSession, cookie: str | None) -> accounts.Session | None:
    """The signed-in session a cookie names, or None. Never raises."""
    return None if cookie is None else await accounts.authenticate(session, cookie)


async def signed_in_user(session: AsyncSession, cookie: str | None) -> User | None:
    """The account a session cookie names, if it still names one."""
    signed_in = await viewer(session, cookie)
    if signed_in is None:
        return None
    return await session.get(User, signed_in.user_id)


async def _current_user(session: SessionDep, namescape_session: SessionCookie = None) -> User:
    user = await signed_in_user(session, namescape_session)
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to do that")
    return user


CurrentUser = Annotated[User, Depends(_current_user)]


async def existing_claimant(
    session: AsyncSession, session_cookie: str | None, guest_cookie: str | None
) -> discoveries.Claimant | None:
    """Whoever is already known, account or guest, without creating anybody.

    Reading must not mint a guest session for somebody who never writes.
    """
    user = await signed_in_user(session, session_cookie)
    if user is not None:
        return discoveries.UserClaimant(user.id)
    guest_id = guests.identify(guest_cookie)
    return None if guest_id is None else discoveries.GuestClaimant(guest_id)


def set_guest_cookie(response: Response, guest: guests.Guest) -> None:
    response.set_cookie(
        GUEST_COOKIE,
        guest.cookie,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=guests.GUEST_TTL_SECONDS,
    )
