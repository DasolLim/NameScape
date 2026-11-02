"""The ASGI app: middleware, lifespan, and the routers in app.routes."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app import observability, ratelimit, scheduler
from app.cache import build_client
from app.routes import ROUTERS
from app.text import StripNulMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Start the scheduled jobs, where this process is the sort that can.

    A long-running server runs them in-process. Serverless does not: every
    function instance would start its own scheduler, so there the same jobs are
    invoked by cron over HTTP. See scheduler.should_run.
    """
    running = None
    if scheduler.should_run():
        running = scheduler.build_scheduler()
        running.start()
        logger.info("scheduler started: %s", [job.id for job in running.get_jobs()])
    try:
        yield
    finally:
        if running is not None:
            running.shutdown(wait=False)


app = FastAPI(title="NameScape API", lifespan=lifespan)

# Middleware cannot use FastAPI dependencies, so the client lives on app.state
# where a test can substitute it.
observability.configure(app)
# Outermost: nothing downstream should ever see a NUL byte.
app.add_middleware(StripNulMiddleware)
app.state.redis = build_client()


@app.middleware("http")
async def attach_request_id(request: Request, call_next: Any) -> Response:
    identifier = observability.new_request_id(request.headers.get("X-Request-ID"))
    token = observability.request_id.set(identifier)
    try:
        response: Response = await call_next(request)
    finally:
        observability.request_id.reset(token)
    response.headers["X-Request-ID"] = identifier
    return response


@app.middleware("http")
async def rate_limit_writes(request: Request, call_next: Any) -> Response:
    """Applied to every write, so a new endpoint is covered by default."""
    if request.method in ratelimit.LIMITED_METHODS:
        try:
            await ratelimit.enforce(request, app.state.redis)
        except HTTPException as limited:
            return JSONResponse(status_code=limited.status_code, content={"detail": limited.detail})
    response: Response = await call_next(request)
    return response


for router in ROUTERS:
    app.include_router(router)
