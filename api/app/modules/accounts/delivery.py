"""Magic link delivery.

With SMTP configured the link is mailed. Without it, the link is logged at
warning level: development has no mail server, and a sign-in link that goes
nowhere is worse than one printed on the console.
"""

import logging
from email.message import EmailMessage
from typing import Final
from urllib.parse import quote

import aiosmtplib

from app.config import settings

logger = logging.getLogger(__name__)

SUBJECT: Final = "Your Toponomicon sign-in link"
EXPIRY_NOTE: Final = "The link works once and expires in 15 minutes."


def sign_in_url(token: str) -> str:
    """Where the link lands. The app completes sign-in from the query."""
    return f"{settings.app_base_url.rstrip('/')}/?token={quote(token, safe='')}"


def build_message(email: str, token: str) -> EmailMessage:
    link = sign_in_url(token)
    message = EmailMessage()
    message["Subject"] = SUBJECT
    message["From"] = settings.smtp_from
    message["To"] = email
    message.set_content(
        f"Sign in to Toponomicon:\n\n{link}\n\n"
        f"{EXPIRY_NOTE}\n\n"
        "If you did not ask for this, ignore it - nothing has changed."
    )
    message.add_alternative(
        f"""<html><body style="font-family:system-ui;color:#0E131C">
        <p>Sign in to <strong>Toponomicon</strong>:</p>
        <p><a href="{link}"
              style="background:#E8A33D;color:#4A320F;padding:12px 20px;
                     border-radius:8px;text-decoration:none;display:inline-block">
           Sign in</a></p>
        <p style="color:#6B665C;font-size:13px">{EXPIRY_NOTE}<br>
           If you did not ask for this, ignore it - nothing has changed.</p>
        </body></html>""",
        subtype="html",
    )
    return message


async def send_magic_link(email: str, token: str) -> None:
    if not settings.smtp_host:
        logger.warning(
            "SMTP is not configured, so no mail was sent. Sign-in link: %s",
            sign_in_url(token),
        )
        return

    await aiosmtplib.send(
        build_message(email, token),
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username or None,
        password=settings.smtp_password or None,
        start_tls=settings.smtp_start_tls,
    )
    logger.info("sign-in link sent", extra={"email": email})
