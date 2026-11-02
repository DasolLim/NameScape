"""HTTP routes, one router per area. Business logic lives in app.modules."""

from fastapi import APIRouter

from app.routes import (
    auth,
    bookmarks,
    contests,
    cron,
    discoveries,
    places,
    puzzle,
    search,
    system,
    users,
    viewport,
)

#: In the order the schema lists them, which keeps generated types stable.
ROUTERS: tuple[APIRouter, ...] = (
    system.router,
    search.router,
    auth.router,
    users.router,
    places.router,
    discoveries.router,
    puzzle.router,
    cron.router,
    viewport.router,
    bookmarks.router,
    contests.router,
)

__all__ = ["ROUTERS"]
