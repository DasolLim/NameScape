"""Builders so any test can create domain rows in one line."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def build_user(session: AsyncSession, *, username: str = "finder", **kwargs: object) -> User:
    user = User(username=username, email=kwargs.get("email", f"{username}@example.test"))
    session.add(user)
    await session.flush()
    return user
