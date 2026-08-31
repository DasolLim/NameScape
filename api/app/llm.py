"""A language model behind one narrow interface.

Deliberately small: one call that asks for JSON and returns None on anything
that is not usable. Two callers need it, both offline, and neither should learn
anything about the provider.

**No request path may call this.** Etymology is resolved once and cached
forever; puzzle clues are generated ninety days ahead and approved by a person.
A model call while a user waits would be slow, nondeterministic, and capable of
failing for everyone at once.
"""

import json
import logging
from typing import Any, Final, Protocol, runtime_checkable

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

#: Generous: this is batch work, and a retry costs more than a slow answer.
_TIMEOUT: Final = 60.0
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

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    async def complete_json(self, prompt: str, *, system: str | None = None) -> Any:
        messages: list[dict[str, str]] = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
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


def build_client() -> LLMClient | None:
    """A client, or None when no key is configured.

    None is a supported state, not a failure: every caller has to work without
    a model, because the tiers above it are the citable ones.
    """
    if not settings.openrouter_api_key:
        return None
    return OpenRouterClient(settings.openrouter_api_key, settings.openrouter_model)
