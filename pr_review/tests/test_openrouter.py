"""Tests for the OpenRouter chat completion client."""
from __future__ import annotations

import json

import pytest

from pr_review import openrouter


def test_call_sends_auth_header(httpx_mock):
    httpx_mock.add_response(
        url="https://openrouter.ai/api/v1/chat/completions",
        method="POST",
        json={
            "choices": [{"message": {"content": "review text <severity>0</severity>"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            "model": "anthropic/claude-sonnet-4-6",
        },
    )

    result = openrouter.complete(
        api_key="test-key",
        model="anthropic/claude-sonnet-4-6",
        messages=[{"role": "user", "content": "hi"}],
    )

    request = httpx_mock.get_request()
    assert request.headers["Authorization"] == "Bearer test-key"
    assert result.content == "review text <severity>0</severity>"
    assert result.prompt_tokens == 100
    assert result.completion_tokens == 50


def test_call_sends_referer_and_title(httpx_mock):
    """OpenRouter recommends these headers for app identification."""
    httpx_mock.add_response(
        url="https://openrouter.ai/api/v1/chat/completions",
        method="POST",
        json={
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "model": "anthropic/claude-sonnet-4-6",
        },
    )

    openrouter.complete(
        api_key="test-key",
        model="anthropic/claude-sonnet-4-6",
        messages=[{"role": "user", "content": "hi"}],
    )

    request = httpx_mock.get_request()
    assert "HTTP-Referer" in request.headers
    assert "X-Title" in request.headers


def test_call_sends_model_and_messages_in_body(httpx_mock):
    httpx_mock.add_response(
        url="https://openrouter.ai/api/v1/chat/completions",
        method="POST",
        json={
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "model": "anthropic/claude-sonnet-4-6",
        },
    )

    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    openrouter.complete(
        api_key="test-key",
        model="anthropic/claude-sonnet-4-6",
        messages=messages,
    )

    request = httpx_mock.get_request()
    body = json.loads(request.content)
    assert body["model"] == "anthropic/claude-sonnet-4-6"
    assert body["messages"] == messages


def test_call_raises_on_http_error(httpx_mock):
    httpx_mock.add_response(
        url="https://openrouter.ai/api/v1/chat/completions",
        method="POST",
        status_code=401,
        json={"error": {"message": "Invalid API key"}},
    )

    with pytest.raises(openrouter.OpenRouterError) as exc_info:
        openrouter.complete(
            api_key="bad",
            model="anthropic/claude-sonnet-4-6",
            messages=[{"role": "user", "content": "hi"}],
        )
    assert "401" in str(exc_info.value) or "Invalid API key" in str(exc_info.value)


def test_estimate_cost_for_sonnet():
    """Cost in USD for a known model + token counts."""
    cost = openrouter.estimate_cost(
        model="anthropic/claude-sonnet-4-6",
        prompt_tokens=10000,
        completion_tokens=1000,
    )
    # 10000 * $3/M = $0.03; 1000 * $15/M = $0.015; total = $0.045
    assert abs(cost - 0.045) < 0.0001


def test_estimate_cost_unknown_model_returns_zero():
    """For models we haven't priced, return 0 rather than raising — marker just shows $0."""
    cost = openrouter.estimate_cost(
        model="unknown/model-x",
        prompt_tokens=1000,
        completion_tokens=500,
    )
    assert cost == 0.0
