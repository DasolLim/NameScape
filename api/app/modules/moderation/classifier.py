"""The Claude Haiku classifier and its circuit breaker. Internal."""

from typing import Final

import anthropic
from pydantic import BaseModel

from app.config import settings

MODEL: Final = "claude-haiku-4-5"
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
any of these categories."""


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


async def classify(text: str) -> Categories:
    """Ask Haiku. Raises on timeout or transport failure; the caller fails closed."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.with_options(timeout=TIMEOUT_SECONDS).messages.parse(
        model=MODEL,
        max_tokens=256,
        system=_SYSTEM,
        messages=[{"role": "user", "content": text}],
        output_format=Categories,
    )
    parsed = response.parsed_output
    if parsed is None:
        raise RuntimeError("classifier returned no structured output")
    return parsed
