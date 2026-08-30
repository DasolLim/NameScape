"""Text arriving from outside, made safe for Postgres.

Postgres text columns cannot contain 0x00, and asyncpg raises rather than
truncating, so an unstripped NUL byte in any parameter is a 500. Contract
fuzzing found this; it is not reachable through the UI.
"""

import re
from typing import Any, Final

_NUL: Final = "\x00"
#: Both the raw byte and its percent-encoded form, which is how it arrives.
_ENCODED_NUL: Final = re.compile(rb"%00|\x00", re.IGNORECASE)


def strip_nul(value: str) -> str:
    return value.replace(_NUL, "")


class StripNulMiddleware:
    """Remove NUL bytes from the query string before anything parses it.

    Done once here rather than per parameter, so a new endpoint cannot
    reintroduce the crash by forgetting to sanitise its own arguments.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") == "http":
            query = scope.get("query_string", b"")
            cleaned = _ENCODED_NUL.sub(b"", query)
            if cleaned != query:
                scope = {**scope, "query_string": cleaned}
        await self.app(scope, receive, send)
