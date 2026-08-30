"""Text arriving from outside, made safe for Postgres.

Postgres text columns cannot contain 0x00, and asyncpg raises rather than
truncating, so an unstripped NUL byte in any parameter is a 500. Contract
fuzzing found this; it is not reachable through the UI.
"""

from typing import Final

_NUL: Final = "\x00"


def strip_nul(value: str) -> str:
    return value.replace(_NUL, "")
