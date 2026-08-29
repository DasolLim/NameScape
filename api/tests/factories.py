"""Builders so any test can create domain rows in one line."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Discovery, User


async def build_user(session: AsyncSession, *, username: str = "finder", **kwargs: object) -> User:
    user = User(username=username, email=kwargs.get("email", f"{username}@example.test"))
    session.add(user)
    await session.flush()
    return user


async def build_discovery(
    session: AsyncSession, *, place_id: int, user_id: uuid.UUID, caption: str = "found it"
) -> Discovery:
    discovery = Discovery(place_id=place_id, user_id=user_id, caption=caption)
    session.add(discovery)
    await session.flush()
    return discovery
