"""Print a signed session cookie for a dev user, for end-to-end tests.

Development only: it signs with the local secret and creates nothing. It
exists so a browser test can exercise the real authenticated endpoints
instead of stubbing them.
"""

import asyncio
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models import User
from app.modules.accounts.service import _session_for


async def main(username: str) -> None:
    async with SessionLocal() as session:
        user = (
            (await session.execute(select(User).where(User.username == username))).scalars().first()
        )
        if user is None:
            raise SystemExit(f"no user named {username}; run `make seed-demo` first")
        print(_session_for(user).cookie)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "demo"))
