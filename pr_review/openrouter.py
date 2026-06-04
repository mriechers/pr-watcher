"""Thin OpenRouter chat-completions client.

OpenRouter's API is OpenAI-compatible — same /chat/completions shape. We use
it to access Anthropic models with centralized billing.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_TIMEOUT_SECONDS = 90

# Per-model pricing in USD per million tokens. Sourced from OpenRouter model list.
_PRICING = {
    "anthropic/claude-sonnet-4-6": {"in": 3.0, "out": 15.0},
    "anthropic/claude-opus-4-7":   {"in": 15.0, "out": 75.0},
}


class OpenRouterError(RuntimeError):
    """Raised when OpenRouter returns a non-2xx response."""


@dataclass
class CompletionResult:
    content: str
    prompt_tokens: int
    completion_tokens: int
    model: str


def complete(
    *,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
) -> CompletionResult:
    """Call OpenRouter and return the model's text + token usage."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/mriechers/pr-watcher",
        "X-Title": "PR Watcher",
    }
    payload = {"model": model, "messages": messages}

    response = httpx.post(_API_URL, headers=headers, json=payload, timeout=_TIMEOUT_SECONDS)

    if response.status_code >= 400:
        raise OpenRouterError(
            f"OpenRouter returned {response.status_code}: {response.text[:500]}"
        )

    body = response.json()
    return CompletionResult(
        content=body["choices"][0]["message"]["content"],
        prompt_tokens=body["usage"]["prompt_tokens"],
        completion_tokens=body["usage"]["completion_tokens"],
        model=body.get("model", model),
    )


def estimate_cost(*, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """USD cost estimate from token counts. Returns 0 for unknown models."""
    pricing = _PRICING.get(model)
    if not pricing:
        return 0.0
    return (
        prompt_tokens * pricing["in"] / 1_000_000
        + completion_tokens * pricing["out"] / 1_000_000
    )
