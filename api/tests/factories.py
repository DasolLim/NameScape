"""Builders so any test can create domain rows in one line."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Discovery, GuestSession, Place, Proposal, User
from app.modules.moderation.normalize import normalize


async def build_user(session: AsyncSession, *, username: str = "finder", **kwargs: object) -> User:
    user = User(username=username, email=kwargs.get("email", f"{username}@example.test"))
    session.add(user)
    await session.flush()
    return user


async def build_guest_session(session: AsyncSession) -> GuestSession:
    guest = GuestSession()
    session.add(guest)
    await session.flush()
    return guest


async def build_discovery(
    session: AsyncSession, *, place_id: int, user_id: uuid.UUID, caption: str = "found it"
) -> Discovery:
    discovery = Discovery(place_id=place_id, user_id=user_id, caption=caption)
    session.add(discovery)
    await session.flush()
    return discovery


async def build_proposal(
    session: AsyncSession, *, place_id: int, user_id: uuid.UUID, text: str
) -> Proposal:
    proposal = Proposal(
        place_id=place_id,
        user_id=user_id,
        text=text,
        normalized_text=normalize(text),
    )
    session.add(proposal)
    await session.flush()
    return proposal


async def build_place(
    session: AsyncSession,
    *,
    name: str = "Dildo",
    geonames_id: int = 6942553,
    country_code: str | None = "CA",
    feature_class: str = "P",
    feature_code: str = "PPL",
    tier: int = 3,
    lon: float = -53.5442,
    lat: float = 47.5766,
    population: int = 0,
) -> Place:
    place = Place(
        geonames_id=geonames_id,
        name=name,
        name_normalized=name.casefold(),
        search_text=name.casefold(),
        alternate_names=[],
        feature_class=feature_class,
        feature_code=feature_code,
        country_code=country_code,
        tier=tier,
        population=population,
        centroid=f"SRID=4326;POINT({lon} {lat})",
    )
    session.add(place)
    await session.flush()
    return place
