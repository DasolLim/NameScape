"""The classifier, which runs on every caption, nickname and correction.

Two properties matter more than anything else here. It **fails closed**: any
transport failure, timeout, missing key or unparseable reply must raise, so the
caller rejects rather than waves the text through. And it is in the **request
path**, unlike the batch model work, so it gets a short timeout of its own
rather than the sixty seconds a nightly job can afford.

No test makes a network call.
"""

from typing import Any

import pytest

from app import llm
from app.config import settings
from app.modules.moderation import classifier


class FakeClient:
    """Stands in for the provider, recording how it was asked."""

    def __init__(self, reply: Any = None, raises: Exception | None = None) -> None:
        self.reply = reply
        self.raises = raises
        self.calls: list[tuple[str, str | None]] = []

    @property
    def model(self) -> str:
        return "fake/moderation-1"

    async def complete_json(self, prompt: str, *, system: str | None = None) -> Any:
        self.calls.append((prompt, system))
        if self.raises is not None:
            raise self.raises
        return self.reply


@pytest.fixture(autouse=True)
def real_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bypass is on in development, and would hide every test here."""
    monkeypatch.setattr(settings, "moderation_dev_bypass", False)
    classifier.breaker.reset()


def use(monkeypatch: pytest.MonkeyPatch, client: FakeClient) -> FakeClient:
    monkeypatch.setattr(classifier, "_client", lambda: client)
    return client


async def test_clean_text_comes_back_with_nothing_flagged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use(
        monkeypatch,
        FakeClient(
            {
                "targets_protected_group": False,
                "targets_private_individual": False,
                "sexual": False,
                "violent": False,
                "spam": False,
            }
        ),
    )

    verdict = await classifier.classify("A cove with a very silly name.")

    assert verdict.any_positive is False


async def test_a_flagged_category_is_carried_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use(monkeypatch, FakeClient({"spam": True}))

    verdict = await classifier.classify("buy cheap maps dot com")

    assert verdict.spam is True
    assert verdict.any_positive is True


async def test_the_submitted_text_and_the_rules_both_reach_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = use(monkeypatch, FakeClient({}))

    await classifier.classify("Dildo, Newfoundland")

    prompt, system = client.calls[0]
    assert "Dildo, Newfoundland" in prompt
    assert system is not None
    # The instruction that keeps the product from moderating away its own
    # premise has to actually be sent.
    assert "toilet humour" in system


async def test_a_transport_failure_raises_so_the_caller_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use(monkeypatch, FakeClient(raises=TimeoutError("took too long")))

    # Propagated rather than swallowed: screen() turns any exception here into
    # a rejection, and a transport failure must reach it.
    with pytest.raises(TimeoutError):
        await classifier.classify("anything at all")


async def test_a_reply_that_is_not_a_verdict_raises_rather_than_passing_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """None is how the client reports a failed call or an unparseable body. It
    must never be read as "nothing was flagged"."""
    use(monkeypatch, FakeClient(None))

    with pytest.raises(classifier.ClassifierUnavailableError):
        await classifier.classify("anything at all")


async def test_a_reply_of_the_wrong_shape_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use(monkeypatch, FakeClient({"spam": "yes please", "violent": []}))

    with pytest.raises(classifier.ClassifierUnavailableError):
        await classifier.classify("anything at all")


async def test_unknown_categories_in_a_reply_are_ignored_not_fatal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model that volunteers an extra field is not a reason to reject text."""
    use(monkeypatch, FakeClient({"spam": False, "invented_category": True}))

    verdict = await classifier.classify("A perfectly ordinary caption.")

    assert verdict.any_positive is False


async def test_no_key_configured_raises_rather_than_accepting_everything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The failure mode this replaces: an unset key silently accepting all text
    would turn the fail-closed pipeline into a fail-open one."""
    # No stub: with no key the real builder returns None, which is the exact
    # production shape of this failure.
    monkeypatch.setattr(settings, "openrouter_api_key", "")

    with pytest.raises(classifier.ClassifierUnavailableError):
        await classifier.classify("anything at all")


async def test_the_development_bypass_still_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "moderation_dev_bypass", True)
    client = use(monkeypatch, FakeClient(raises=AssertionError("must not be called")))

    verdict = await classifier.classify("anything at all")

    assert verdict.any_positive is False
    assert client.calls == []


def test_the_request_path_timeout_is_short_not_the_batch_one() -> None:
    """Moderation blocks a person pressing a button; the batch jobs do not."""
    assert classifier.TIMEOUT_SECONDS <= 10
    assert classifier.TIMEOUT_SECONDS < llm.BATCH_TIMEOUT_SECONDS


def test_nothing_here_imports_the_anthropic_sdk() -> None:
    """Moderation runs on OpenRouter now, so one key covers every model call."""
    import inspect

    source = inspect.getsource(classifier)

    assert "anthropic" not in source.casefold()
