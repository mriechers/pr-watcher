"""Build the system + user messages for the OpenRouter chat completion call.

Loads the bot-voice template, substitutes tier/first_run/ci_state placeholders,
and packages it with the PR diff as a two-message list.
"""
from __future__ import annotations

import pathlib

_TEMPLATE_PATH = pathlib.Path(__file__).parent / "templates" / "bot-voice.md"

_FIRST_RUN_NOTE = (
    "This is the **first review** on this PR. Frame any findings as discovery "
    "items rather than urgent merge-blockers — first-pass CI surfaces things "
    "(unrotated credentials, retrofit type issues) that are cleanup, not regressions."
)


def build(
    *,
    diff: str,
    tier: str,
    ci_state: str,
    first_run: bool,
    pr_title: str,
    pr_body: str,
) -> list[dict[str, str]]:
    """Return [{role: system, content: ...}, {role: user, content: ...}]."""
    template = _TEMPLATE_PATH.read_text()
    system_prompt = (
        template
        .replace("{{tier}}", tier)
        .replace("{{ci_state}}", ci_state)
        .replace("{{first_run_note}}", _FIRST_RUN_NOTE if first_run else "")
        .strip()
    )

    user_content = _user_message(pr_title, pr_body, diff)

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def _user_message(pr_title: str, pr_body: str, diff: str) -> str:
    parts = [f"# PR: {pr_title}"]
    if pr_body.strip():
        parts.append("\n## Description\n")
        parts.append(pr_body.strip())
    parts.append("\n## Diff\n")
    parts.append("```diff")
    parts.append(diff)
    parts.append("```")
    return "\n".join(parts)
