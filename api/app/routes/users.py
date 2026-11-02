"""Public profiles, passports, and the share card."""

from dataclasses import asdict
from datetime import datetime
from typing import Final

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules import accounts
from app.modules.accounts import share_card
from app.routes.deps import SessionDep, errors
from app.text import strip_nul

router = APIRouter()

SHARE_CARD_MAX_AGE: Final = 60 * 60


class Profile(BaseModel):
    username: str
    joined_at: datetime
    discoveries: int


class PassportResponse(BaseModel):
    username: str
    discoveries: int
    first_finds: int
    countries: dict[str, int]
    completion: dict[str, float]
    streak_days: int
    streak_at_risk: bool


async def _passport_or_404(session: AsyncSession, username: str) -> accounts.Passport:
    found = await accounts.passport(session, strip_nul(username))
    if found is None:
        raise HTTPException(status_code=404, detail="No such user")
    return found


@router.get(
    "/api/passport/{username}/card.png",
    response_class=Response,
    responses=errors(404),
)
async def read_share_card(username: str, session: SessionDep) -> Response:
    found = await _passport_or_404(session, username)
    return Response(
        content=share_card.render(found),
        media_type="image/png",
        headers={"Cache-Control": f"public, max-age={SHARE_CARD_MAX_AGE}"},
    )


@router.get("/api/users/{username}", responses=errors(404))
async def read_profile(username: str, session: SessionDep) -> Profile:
    found = await accounts.profile(session, strip_nul(username))
    if found is None:
        raise HTTPException(status_code=404, detail="No such user")
    return Profile(**asdict(found))


@router.get("/api/passport/{username}", responses=errors(404))
async def read_passport(username: str, session: SessionDep) -> PassportResponse:
    return PassportResponse(**asdict(await _passport_or_404(session, username)))
