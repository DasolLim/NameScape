"""ASGI entrypoint for serverless platforms.

Vercel discovers a function per file under this directory and routes /api/* to
this one. The app is defined in app/main.py and is unchanged by being hosted
here: this file only gives the platform something to import.

Nothing starts a scheduler here. RUN_SCHEDULER stays false on serverless, where
each function instance would start one of its own; the same jobs are invoked by
cron at /api/cron/{job} instead.
"""

from app.main import app

__all__ = ["app"]
