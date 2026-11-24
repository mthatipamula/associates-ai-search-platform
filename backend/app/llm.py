"""Claude client factory: Anthropic API or Amazon Bedrock.

LLM_PROVIDER=anthropic -> anthropic.Anthropic()  (ANTHROPIC_API_KEY or `ant auth login`)
LLM_PROVIDER=bedrock   -> anthropic.AnthropicBedrockMantle(aws_region=...)
                          (IAM credentials; model id gets the "anthropic." prefix)
LLM_PROVIDER=none      -> no LLM; callers use extractive / rule-based fallbacks
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from .config import settings


def llm_enabled() -> bool:
    return settings.llm_provider in ("anthropic", "bedrock")


@lru_cache(maxsize=1)
def _client():
    import anthropic

    if settings.llm_provider == "bedrock":
        return anthropic.AnthropicBedrockMantle(aws_region=settings.aws_region)
    return anthropic.Anthropic()


def model_id() -> str:
    m = settings.llm_model
    if settings.llm_provider == "bedrock" and not m.startswith("anthropic."):
        m = f"anthropic.{m}"
    return m


def create_message(**kwargs: Any):
    """messages.create with project defaults.

    On the Anthropic API we opt into server-side refusal fallbacks so a
    safety decline is retried on a fallback model inside the same call.
    That parameter is not available on Bedrock, so it is only sent to the
    Anthropic API.
    """
    params: dict[str, Any] = {
        "model": model_id(),
        "max_tokens": 16000,
        "output_config": {"effort": settings.llm_effort},
        **kwargs,
    }
    client = _client()
    if settings.llm_provider == "anthropic":
        return client.beta.messages.create(
            betas=["server-side-fallback-2026-07-01"], fallbacks="default", **params
        )
    return client.messages.create(**params)


def text_of(response) -> str:
    return "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
