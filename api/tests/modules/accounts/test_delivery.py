import aiosmtplib
import pytest

from app.config import settings
from app.modules.accounts import delivery


@pytest.fixture(autouse=True)
def unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(settings, "app_base_url", "http://localhost:5173")


def test_the_link_points_at_the_app_with_the_token() -> None:
    link = delivery.sign_in_url("abc123")

    assert link == "http://localhost:5173/?token=abc123"


def test_a_token_needing_escaping_is_encoded() -> None:
    assert "%2F" in delivery.sign_in_url("a/b")


def test_the_message_carries_the_link_and_says_it_expires() -> None:
    message = delivery.build_message("finder@example.com", "abc123")

    body = message.get_body(preferencelist=("plain",))
    assert body is not None
    text = body.get_content()
    assert delivery.sign_in_url("abc123") in text
    assert "15 minutes" in text
    assert message["To"] == "finder@example.com"
    assert message["Subject"]


async def test_without_smtp_configured_the_link_is_logged_not_swallowed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Development has no mail server; the link must still be reachable."""
    with caplog.at_level("WARNING"):
        await delivery.send_magic_link("finder@example.com", "abc123")

    assert delivery.sign_in_url("abc123") in caplog.text


async def test_a_configured_server_is_actually_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    sent: list[object] = []

    async def capture(message: object, **kwargs: object) -> None:
        sent.append((message, kwargs))

    monkeypatch.setattr(aiosmtplib, "send", capture)

    await delivery.send_magic_link("finder@example.com", "abc123")

    assert len(sent) == 1
