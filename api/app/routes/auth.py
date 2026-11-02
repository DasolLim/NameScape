"""Passwordless sign-in."""

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, EmailStr

from app.modules import accounts
from app.routes.deps import (
    GUEST_COOKIE,
    SESSION_COOKIE,
    WRITE_ERRORS,
    GuestCookie,
    RedisDep,
    SessionCookie,
    SessionDep,
    errors,
    viewer,
)

router = APIRouter()


class MagicLinkRequest(BaseModel):
    email: EmailStr


class SessionRequest(BaseModel):
    token: str


class Me(BaseModel):
    username: str


@router.post("/api/auth/magic-link", status_code=204, responses=errors(*WRITE_ERRORS))
async def request_magic_link(
    body: MagicLinkRequest, session: SessionDep, redis: RedisDep
) -> Response:
    try:
        await accounts.request_magic_link(session, redis, body.email)
    except accounts.TooManyRequestsError:
        # Deliberately vague: the limit is not a hint to work around.
        raise HTTPException(status_code=429, detail="Too many requests") from None
    await session.commit()
    return Response(status_code=204)


@router.post("/api/auth/session", responses=errors(401, *WRITE_ERRORS))
async def create_session(
    body: SessionRequest,
    session: SessionDep,
    response: Response,
    namescape_guest: GuestCookie = None,
) -> Me:
    # The guest cookie goes in so authenticate() can adopt the claim behind it.
    signed_in = await accounts.authenticate(session, body.token, namescape_guest)
    if signed_in is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    await session.commit()

    if namescape_guest is not None:
        # Spent whether or not it carried a claim, and leaving it would let a
        # signed-out visitor in this browser inherit somebody's old session.
        response.delete_cookie(GUEST_COOKIE)

    response.set_cookie(
        SESSION_COOKIE,
        signed_in.cookie,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=accounts.SESSION_TTL_SECONDS,
    )
    return Me(username=signed_in.username)


@router.get("/api/auth/me")
async def read_me(session: SessionDep, namescape_session: SessionCookie = None) -> Me | None:
    signed_in = await viewer(session, namescape_session)
    return None if signed_in is None else Me(username=signed_in.username)
