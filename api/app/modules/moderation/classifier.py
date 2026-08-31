"""The moderation classifier and its circuit breaker. Internal.

Runs on every caption, nickname and etymology correction, which makes it the
one model call in a request path. Two consequences: it gets a short timeout of
its own rather than the batch client's sixty seconds, and it **fails closed** -
a timeout, a transport error, a missing key or a reply of the wrong shape all
raise, so the caller refuses the text rather than waving it through.

Reads None as a refusal, which is the opposite of what the offline callers do
with it. There, no model means fall back to a citable source; here, no model
means nothing screened the text.
"""

import logging
from typing import Any, Final

from pydantic import BaseModel, ValidationError

from app import llm
from app.config import settings

logger = logging.getLogger(__name__)

#: Short, because somebody is waiting on a button press.
TIMEOUT_SECONDS: Final = 5.0
FAILURE_THRESHOLD: Final = 5

_SYSTEM: Final = """You screen short user-submitted text for a map product where
people nickname real places. Judge only the submitted text.

Return true for a category only when the text clearly matches it:
- targets_protected_group: demeans people by race, ethnicity, religion,
  nationality, gender, sexuality, disability, or caste.
- targets_private_individual: names or identifies a private person.
- sexual: sexually explicit content. Innuendo in a place name is not enough.
- violent: threatens or glorifies violence.
- spam: advertising, links, or unrelated promotion.

Absurdity, rudeness and toilet humour about a place are not, by themselves,
any of these categories.

Return only JSON, with those five keys and boolean values."""


class ClassifierUnavailableError(RuntimeError):
    """Nothing screened the text. The caller must refuse it."""


class Categories(BaseModel):
    targets_protected_group: bool = False
    targets_private_individual: bool = False
    sexual: bool = False
    violent: bool = False
    spam: bool = False

    @property
    def any_positive(self) -> bool:
        return any(
            (
                self.targets_protected_group,
                self.targets_private_individual,
                self.sexual,
                self.violent,
                self.spam,
            )
        )


class CircuitBreaker:
    """Stops spending calls on a dependency that has already failed repeatedly."""

    def __init__(self, threshold: int) -> None:
        self._threshold = threshold
        self._failures = 0

    @property
    def is_open(self) -> bool:
        return self._failures >= self._threshold

    def record_success(self) -> None:
        self._failures = 0

    def record_failure(self) -> None:
        self._failures += 1

    def reset(self) -> None:
        self._failures = 0


breaker = CircuitBreaker(FAILURE_THRESHOLD)


#: Minimal, not because the answer matters less but because somebody is
#: waiting. Measured live: the same verdict in 1.1s rather than 3.7s, against a
#: 5s fail-closed timeout. Screening a sentence is classification, not a task
#: that rewards deliberation.
_REASONING_EFFORT: Final = "minimal"


def _client() -> llm.LLMClient | None:
    return llm.build_client(settings.moderation_model, TIMEOUT_SECONDS, _REASONING_EFFORT)


def _verdict_from(reply: Any) -> Categories:
    """Parse a reply, or raise. An unreadable answer is not an absence of findings."""
    if not isinstance(reply, dict):
        raise ClassifierUnavailableError("classifier returned no usable verdict")
    try:
        # Unknown keys are ignored by the model: a volunteered extra category is
        # not a reason to refuse somebody's caption.
        return Categories.model_validate(reply)
    except ValidationError as malformed:
        raise ClassifierUnavailableError("classifier returned the wrong shape") from malformed


async def classify(text: str) -> Categories:
    """Screen one piece of text. Raises rather than guessing; caller fails closed."""
    if settings.moderation_dev_bypass:
        logger.warning("MODERATION CLASSIFIER BYPASSED - development only, never production")
        return Categories()

    client = _client()
    if client is None:
        raise ClassifierUnavailableError("no model configured to screen text")

    return _verdict_from(await client.complete_json(text, system=_SYSTEM))
