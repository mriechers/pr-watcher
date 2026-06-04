"""Tests for marker serialization and parsing."""
from __future__ import annotations

from pr_review import marker


def test_serialize_includes_all_fields():
    data = {
        "sha": "abc123def456",
        "ts": "2026-05-13T19:00:00Z",
        "model": "anthropic/claude-sonnet-4-6",
        "tier": "a",
        "prompt_tokens": 12450,
        "completion_tokens": 634,
        "cost_usd": 0.0473,
        "severity": 2,
        "ci_state": "green",
        "first_run": False,
    }
    result = marker.serialize(data)
    assert result.startswith("<!-- pr-watch-agent:")
    assert result.rstrip().endswith("-->")
    for key, value in data.items():
        assert f"{key}=" in result


def test_parse_extracts_all_fields():
    raw = """<!-- pr-watch-agent:
  sha=abc123def456
  ts=2026-05-13T19:00:00Z
  model=anthropic/claude-sonnet-4-6
  tier=a
  prompt_tokens=12450
  completion_tokens=634
  cost_usd=0.0473
  severity=2
  ci_state=green
  first_run=false
-->"""
    result = marker.parse(raw)
    assert result["sha"] == "abc123def456"
    assert result["model"] == "anthropic/claude-sonnet-4-6"
    assert result["tier"] == "a"
    assert result["prompt_tokens"] == 12450
    assert result["completion_tokens"] == 634
    assert result["cost_usd"] == 0.0473
    assert result["severity"] == 2
    assert result["first_run"] is False


def test_round_trip():
    original = {
        "sha": "deadbeef",
        "ts": "2026-05-13T19:00:00Z",
        "model": "anthropic/claude-sonnet-4-6",
        "tier": "b",
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "cost_usd": 0.001,
        "severity": 0,
        "ci_state": "green",
        "first_run": True,
    }
    serialized = marker.serialize(original)
    parsed = marker.parse(serialized)
    assert parsed == original


def test_find_in_comment_body():
    body = """<!-- pr-watch-agent:
  sha=abc123
  ts=2026-05-13T19:00:00Z
  model=anthropic/claude-sonnet-4-6
  tier=a
  prompt_tokens=10
  completion_tokens=5
  cost_usd=0.001
  severity=1
  ci_state=green
  first_run=false
-->

## Claude review

Looks good!"""
    result = marker.find_in_body(body)
    assert result is not None
    assert result["sha"] == "abc123"


def test_find_returns_none_when_absent():
    assert marker.find_in_body("Just a regular comment.") is None


def test_find_sha_for_existing_marker():
    """Used by dedup: given list of comment bodies, return SHAs already reviewed."""
    bodies = [
        "<!-- pr-watch-agent:\n  sha=aaa\n  ts=2026-01-01T00:00:00Z\n  model=x\n  tier=a\n  prompt_tokens=0\n  completion_tokens=0\n  cost_usd=0\n  severity=0\n  ci_state=green\n  first_run=true\n-->",
        "Regular comment",
        "<!-- pr-watch-agent:\n  sha=bbb\n  ts=2026-01-02T00:00:00Z\n  model=x\n  tier=a\n  prompt_tokens=0\n  completion_tokens=0\n  cost_usd=0\n  severity=0\n  ci_state=green\n  first_run=false\n-->",
    ]
    shas = marker.shas_in_comments(bodies)
    assert shas == {"aaa", "bbb"}
