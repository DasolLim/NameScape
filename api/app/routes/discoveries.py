"""Claiming places, with or without an account."""

from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app import ratelimit
from app.config import settings
from app.modules import discoveries
from app.modules.accounts import guests
from app.routes.deps import (
    WRITE_ERRORS,
    GuestCookie,
    RedisDep,
    SessionCookie,
    SessionDep,
    errors,
    existing_claimant,
    set_guest_cookie,
    signed_in_user,
)

router = APIRouter()


class ClaimRequest(BaseModel):
    place_id: int
    caption: str = Field(min_length=1, max_length=140)
    etymology: str | None = None


class DiscoveryResponse(BaseModel):
    id: int
    place_id: int
    finder: str
    caption: str
    #: Set only for a guest claim: when the place is released again.
    expires_at: datetime | None = None


class UserDiscoveryResponse(BaseModel):
    id: int
    place_id: int
    place_name: str
    country_code: str | None
    caption: str
    created_at: datetime
    #: Set only on a guest claim: when this place is released again.
    expires_at: datetime | None = None


class UserDiscoveriesResponse(BaseModel):
    discoveries: list[UserDiscoveryResponse]


@router.get("/api/discoveries")
async def read_my_discoveries(
    session: SessionDep,
    namescape_session: SessionCookie = None,
    namescape_guest: GuestCookie = None,
) -> UserDiscoveriesResponse:
    """Whatever the caller has claimed, account or not.

    A guest has to be able to read their own claim: it is the only way the
    deadline survives a reload, and the only way the interface can explain the
    claim control instead of offering a second one. Not a 401 either way -
    a visitor who has claimed nothing has claimed nothing.
    """
    claimant = await existing_claimant(session, namescape_session, namescape_guest)
    found = [] if claimant is None else await discoveries.for_user(session, claimant)
    return UserDiscoveriesResponse(
        discoveries=[UserDiscoveryResponse(**asdict(item)) for item in found]
    )


async def _spend_guest_allowance(request: Request, redis: Redis) -> None:
    """Three claims per address per day, hashed, in Redis only.

    Charged per attempt rather than per success, because counting only the
    ones that stuck would let one address try places all day until three did.
    """
    peer = request.client.host if request.client else "unknown"
    address = ratelimit.address_of_client(peer, request.headers.get("X-Forwarded-For"))

    try:
        used = await ratelimit.count(
            redis, ratelimit.key_for(address, "guest-claim"), ratelimit.DAY_SECONDS
        )
    except (RedisError, OSError) as unreachable:
        # Without Redis the allowance cannot be counted, and an uncounted
        # guest claim is the one thing this limit exists to prevent.
        raise HTTPException(
            status_code=503, detail="Writes are temporarily unavailable"
        ) from unreachable

    if used > settings.guest_claims_per_day:
        raise HTTPException(status_code=429, detail="Too many requests")


@router.post(
    "/api/discoveries", status_code=201, responses=errors(403, 409, 422, 428, *WRITE_ERRORS)
)
async def create_discovery(
    body: ClaimRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    redis: RedisDep,
    namescape_session: SessionCookie = None,
    namescape_guest: GuestCookie = None,
) -> DiscoveryResponse:
    """Claiming is the one write that does not require an account."""
    user = await signed_in_user(session, namescape_session)

    claimant: discoveries.Claimant
    guest: guests.Guest | None = None
    if user is not None:
        claimant = discoveries.UserClaimant(user.id)
        finder = user.username
    else:
        await _spend_guest_allowance(request, redis)
        # Written in the claim's own transaction, so a claim that fails does
        # not leave a session behind for a cookie to point at.
        guest = await guests.resolve(session, namescape_guest)
        claimant = discoveries.GuestClaimant(guest.id)
        finder = discoveries.GUEST_FINDER

    try:
        discovery = await discoveries.claim(
            session, body.place_id, claimant, body.caption, body.etymology
        )
    except discoveries.AlreadyClaimedError:
        raise HTTPException(status_code=409, detail="Someone found this one first") from None
    except discoveries.GuestLimitReachedError:
        raise HTTPException(
            status_code=403,
            detail="You already have a claim. Create an account to keep it and find more.",
        ) from None
    except discoveries.NotEligibleError as blocked:
        raise HTTPException(status_code=403, detail=str(blocked)) from None
    except discoveries.EtymologyRequiredError as needed:
        raise HTTPException(status_code=428, detail=str(needed)) from None
    except discoveries.CaptionRejectedError:
        # Deliberately vague: naming the rule teaches people to beat it.
        raise HTTPException(status_code=422, detail="That caption cannot be used") from None

    await session.commit()
    if guest is not None:
        # Only now, with the claim committed, is the cookie worth holding on to.
        set_guest_cookie(response, guest)

    return DiscoveryResponse(
        id=discovery.id,
        place_id=discovery.place_id,
        finder=finder,
        caption=discovery.caption,
        expires_at=discovery.expires_at,
    )
