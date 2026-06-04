"""Serialize and parse the rich HTML-comment marker on PR review comments.

Every review comment leads with a marker block carrying the metadata needed
to make the comment self-describing for later audit. The PR comments are the
dataset — no parallel store.
"""
from __future__ import annotations

import re
from typing import Any

_MARKER_RE = re.compile(
    r"<!--\s*pr-watch-agent:\s*\n(?P<body>.*?)\n\s*-->",
    re.DOTALL,
)
_FIELD_RE = re.compile(r"^\s*([a-z_]+)=(.*?)\s*$", re.MULTILINE)

_INT_FIELDS = {"prompt_tokens", "completion_tokens", "severity"}
_FLOAT_FIELDS = {"cost_usd"}
_BOOL_FIELDS = {"first_run"}

_FIELD_ORDER = [
    "sha", "ts", "model", "tier",
    "prompt_tokens", "completion_tokens", "cost_usd",
    "severity", "ci_state", "first_run",
]


def serialize(data: dict[str, Any]) -> str:
    """Render the metadata dict as the HTML-comment marker block."""
    lines = ["<!-- pr-watch-agent:"]
    for key in _FIELD_ORDER:
        if key not in data:
            continue
        value = data[key]
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        else:
            rendered = str(value)
        lines.append(f"  {key}={rendered}")
    lines.append("-->")
    return "\n".join(lines)


def parse(raw: str) -> dict[str, Any]:
    """Parse a marker block string into a typed dict."""
    match = _MARKER_RE.search(raw)
    if not match:
        raise ValueError("No pr-watch-agent marker found in input")
    return _parse_fields(match.group("body"))


def find_in_body(body: str) -> dict[str, Any] | None:
    """Search a comment body for a marker. Returns parsed dict or None."""
    match = _MARKER_RE.search(body)
    if not match:
        return None
    return _parse_fields(match.group("body"))


def shas_in_comments(comment_bodies: list[str]) -> set[str]:
    """Return the set of SHAs that already have a pr-watch-agent marker."""
    shas: set[str] = set()
    for body in comment_bodies:
        parsed = find_in_body(body)
        if parsed and "sha" in parsed:
            shas.add(parsed["sha"])
    return shas


def _parse_fields(body: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for match in _FIELD_RE.finditer(body):
        key, raw_value = match.group(1), match.group(2)
        result[key] = _coerce(key, raw_value)
    return result


def _coerce(key: str, raw_value: str) -> Any:
    if key in _BOOL_FIELDS:
        return raw_value.lower() == "true"
    if key in _INT_FIELDS:
        return int(raw_value)
    if key in _FLOAT_FIELDS:
        return float(raw_value)
    return raw_value
