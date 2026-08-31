"""The provider client, and the one knob that matters for latency.

Moderation is the only model call with a person waiting on it. Measured against
the live provider, gpt-5-mini answers a screening prompt in 3.7s at its default
reasoning effort and 1.1s at minimal, with the same verdict. Against a 5s
fail-closed timeout the difference is whether a legitimate caption is refused.

The offline callers want the opposite trade: they have ninety days, and a
better answer is worth the wait.
"""

from app import llm
from app.config import settings
from app.modules.moderation import classifier


def test_a_batch_client_asks_for_the_models_full_effort() -> None:
    client = llm.OpenRouterClient("key", "openai/gpt-5-mini")

    payload = client.payload_for("a prompt", system="rules")

    assert "reasoning_effort" not in payload
    assert payload["model"] == "openai/gpt-5-mini"
    assert payload["response_format"] == {"type": "json_object"}


def test_a_client_can_be_built_for_speed_instead() -> None:
    client = llm.OpenRouterClient("key", "openai/gpt-5-mini", reasoning_effort="minimal")

    assert client.payload_for("a prompt")["reasoning_effort"] == "minimal"


def test_the_system_prompt_is_only_sent_when_there_is_one() -> None:
    client = llm.OpenRouterClient("key", "m")

    assert [m["role"] for m in client.payload_for("p", system="s")["messages"]] == [
        "system",
        "user",
    ]
    assert [m["role"] for m in client.payload_for("p")["messages"]] == ["user"]


def test_the_moderation_client_is_built_for_speed(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Otherwise a slow screening call refuses somebody's caption."""
    monkeypatch.setattr(settings, "openrouter_api_key", "key")

    built = classifier._client()

    assert isinstance(built, llm.OpenRouterClient)
    assert built.payload_for("text")["reasoning_effort"] == "minimal"
