"""A language model behind one narrow interface.

Deliberately small: one call that asks for JSON and returns None on anything
that is not usable. Every caller goes through the same provider, so one key
covers the lot.

**Two of the three callers are offline, and must stay that way.** Etymology is
resolved once and cached forever; puzzle clues are drafted ninety days ahead
and approved by a person. A model call in either of those paths while a user
waits would be slow, nondeterministic, and able to fail for everyone at once.

Moderation is the exception, and always was: screening text somebody just typed
cannot be done in advance. It therefore builds its own client with a short
timeout, and treats a None reply as a failure rather than as an absence of
findings. See modules/moderation/classifier.py.
"""

import json
import logging
from typing import Any, Final, Protocol, runtime_checkable

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

#: Generous, for batch work: a retry costs more than a slow answer. Callers in
#: a request path pass their own, much shorter.
BATCH_TIMEOUT_SECONDS: Final = 60.0
_ENDPOINT: Final = "https://openrouter.ai/api/v1/chat/completions"


@runtime_checkable
class LLMClient(Protocol):
    """What callers may rely on. Anything else is the provider's business."""

    @property
    def model(self) -> str:
        """Identifier stored beside whatever the model produced."""
        ...

    async def complete_json(self, prompt: str, *, system: str | None = None) -> Any:
        """Parsed JSON, or None when the call or the parse failed."""
        ...


class OpenRouterClient:
    """OpenRouter, chosen because this is batch work.

    Roughly a few hundred calls a year, so unit cost is irrelevant and model
    quality is the only thing that matters.
    """

    def __init__(
        self, api_key: str, model: str, timeout_seconds: float = BATCH_TIMEOUT_SECONDS
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds

    @property
    def model(self) -> str:
        return self._model

    async def complete_json(self, prompt: str, *, system: str | None = None) -> Any:
        messages: list[dict[str, str]] = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    _ENDPOINT,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "model": self._model,
                        "messages": messages,
                        "response_format": {"type": "json_object"},
                    },
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, ValueError, KeyError, IndexError):
            logger.exception("model call failed")
            return None

        try:
            return json.loads(content)
        except ValueError:
            logger.warning("model returned content that is not JSON")
            return None


def build_client(
    model: str | None = None, timeout_seconds: float = BATCH_TIMEOUT_SECONDS
) -> LLMClient | None:
    """A client, or None when no key is configured.

    For the offline callers None is a supported state rather than a failure:
    the etymology tiers above the model are the citable ones. Moderation reads
    None as a refusal instead, because unscreened text must not pass.
    """
    if not settings.openrouter_api_key:
        return None
    return OpenRouterClient(
        settings.openrouter_api_key, model or settings.openrouter_model, timeout_seconds
    )
