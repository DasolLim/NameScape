"""Scheduled jobs over HTTP, for platforms with no long-running process."""

from hmac import compare_digest
from typing import Final

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app import scheduler
from app.config import settings
from app.routes.deps import RedisDep, SessionDep, errors

router = APIRouter()


class CronResult(BaseModel):
    job: str
    changed: int


#: The scheduled work, by name. Each already takes its own Redis lock, so an
#: overlapping invocation is safe whether it came from a timer or from cron.
_CRON_JOBS: Final = {
    "resolve-due": scheduler.resolve_due_once,
    "release-expired": scheduler.release_expired_once,
    "puzzle-rollover": scheduler.roll_over_once,
}


@router.get("/api/cron/{job}", responses=errors(401, 404))
async def run_scheduled_job_get(
    job: str, request: Request, session: SessionDep, redis: RedisDep
) -> CronResult:
    """Vercel's scheduler invokes with GET. See run_scheduled_job."""
    return await run_scheduled_job(job, request, session, redis)


@router.post("/api/cron/{job}", responses=errors(401, 404))
async def run_scheduled_job(
    job: str, request: Request, session: SessionDep, redis: RedisDep
) -> CronResult:
    """Run one scheduled job. For platforms with no long-running process.

    Declared for GET as well, because Vercel's scheduler invokes with GET and
    does not follow redirects: POST alone would deploy cleanly and never run
    once. Two endpoints rather than one multi-method route, because FastAPI
    gives both methods of a multi-method route the same operation id, and the
    generated frontend types then fail to compile on a duplicate identifier.

    Also the way to force a job by hand, which is what makes a plan with
    once-a-day cron usable: a contest can be resolved on demand rather than
    waited for. Cron delivery is best effort and may miss a run or repeat one,
    which is safe here: each job takes a Redis lock and each is idempotent.

    Fails closed on an unset secret. These endpoints resolve contests and
    release claims, so an open one would be a way to force either at will.
    """
    supplied = (request.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
    if not settings.cron_secret or not compare_digest(supplied, settings.cron_secret):
        raise HTTPException(status_code=401, detail="Not authorised")

    runner = _CRON_JOBS.get(job)
    if runner is None:
        raise HTTPException(status_code=404, detail="No such job")

    return CronResult(job=job, changed=await runner(redis, session))
