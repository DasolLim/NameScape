"""Magic link delivery. Swapped for a real mailer before launch."""

import logging

logger = logging.getLogger(__name__)


async def send_magic_link(email: str, token: str) -> None:
    logger.info("magic link issued", extra={"email": email, "token": token})
