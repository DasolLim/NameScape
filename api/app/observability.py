"""Request identity, metrics and error reporting.

The runbook needs four numbers: how slow search is, whether the viewport
cache is working, whether contests are resolving, and how much moderation is
rejecting. Everything here exists to answer one of those.
"""

import logging
import uuid
from contextvars import ContextVar
from typing import Any, Final

import sentry_sdk
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest

from app.config import settings

REGISTRY: Final = CollectorRegistry()

search_seconds: Final = Histogram(
    "namescape_search_seconds",
    "Time spent answering a gazetteer search.",
    registry=REGISTRY,
)
viewport_cache_total: Final = Counter(
    "namescape_viewport_cache_total",
    "Viewport lookups by cache outcome.",
    ["outcome"],
    registry=REGISTRY,
)
contests_resolved_total: Final = Counter(
    "namescape_contests_resolved_total",
    "Contests closed by the scheduler.",
    registry=REGISTRY,
)
moderation_rejected_total: Final = Counter(
    "namescape_moderation_rejected_total",
    "Submissions refused by moderation.",
    registry=REGISTRY,
)

#: Bound per request so every log line can be traced end to end.
request_id: ContextVar[str] = ContextVar("request_id", default="-")


def new_request_id(supplied: str | None) -> str:
    """Propagate a caller's id when it gives one; otherwise mint a fresh one."""
    return supplied or uuid.uuid4().hex


def cache_events(outcome: str) -> float:
    """Current count for one cache outcome. Used by tests and the runbook."""
    for metric in REGISTRY.collect():
        if metric.name != "namescape_viewport_cache":
            continue
        for sample in metric.samples:
            if sample.labels.get("outcome") == outcome and sample.name.endswith("_total"):
                return float(sample.value)
    return 0.0


def render_metrics() -> bytes:
    return generate_latest(REGISTRY)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


def configure(app: Any) -> None:
    """Structured logs with a request id, and Sentry when a DSN is present."""
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s %(message)s")
    )
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)

    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1)
